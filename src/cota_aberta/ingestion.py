"""Módulo de ingestão e validação de arquivos de informes diários da CVM."""

import csv
import hashlib
import math
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


def sanitize_source_url(url: str | None) -> str:
    """Remove credenciais, parâmetros de consulta e fragmentos de uma URL de origem para auditoria segura."""
    if not url:
        return "local"
    url_str = str(url).strip()
    try:
        parts = urllib.parse.urlsplit(url_str)
        if not parts.scheme and not parts.netloc:
            clean_parts = parts._replace(query="", fragment="")
            return urllib.parse.urlunsplit(clean_parts)
        hostname = parts.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            netloc = f"[{hostname}]"
        else:
            netloc = hostname
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
        clean_parts = parts._replace(netloc=netloc, query="", fragment="")
        return urllib.parse.urlunsplit(clean_parts)
    except Exception:
        raise ValueError(
            "Falha ao sanitizar URL de origem: endereço malformado ou credenciais inválidas."
        ) from None


def parse_cnpj(val: Any) -> str | None:
    """Normaliza o CNPJ mantendo apenas dígitos com 14 caracteres. Rejeita caracteres alfabéticos ou não formatados."""
    if val is None:
        return None
    field_text = str(val).strip()
    if not field_text or not re.match(r"^[\d./\-\s]+$", field_text):
        return None
    digits = re.sub(r"\D", "", field_text)
    if not digits or len(digits) > 14:
        return None
    return digits.zfill(14)


def parse_subclass(val: Any) -> str:
    """Normaliza o identificador de subclasse. Preserva valores como '0' e converte vazios/nulos em string vazia."""
    if val is None:
        return ""
    field_text = str(val).strip()
    if field_text.upper() in ("NULL", "NONE", "NAN"):
        return ""
    return field_text


def parse_date(val: Any) -> str | None:
    """Valida e normaliza datas no padrão ISO YYYY-MM-DD. Rejeita e retorna None para datas inválidas."""
    if not val:
        return None
    field_text = str(val).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", field_text):
        try:
            datetime.strptime(field_text, "%Y-%m-%d")
            return field_text
        except ValueError:
            return None
    if re.match(r"^\d{8}$", field_text):
        try:
            date_obj = datetime.strptime(field_text, "%Y%m%d")
            return date_obj.strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def parse_numeric(val: Any) -> tuple[float | None, bool]:
    """
    Converte valores numéricos aceitando ponto ou vírgula como separador decimal.
    Retorna (valor_float_ou_none, foi_invalido).
    Campos vazios ou indicativos de nulo retornam (None, False).
    Valores textuais não numéricos ou não finitos (inf, -inf, nan) retornam (None, True).
    """
    if val is None:
        return None, False
    field_text = str(val).strip()
    if not field_text or field_text.upper() in ("NULL", "NONE", "NAN", "NA", "N/A", "--", "-"):
        return None, False
    normalized_str = field_text.replace(",", ".")
    try:
        parsed_float = float(normalized_str)
        if math.isfinite(parsed_float):
            return parsed_float, False
        return None, True
    except (ValueError, TypeError):
        return None, True


def parse_integer(val: Any) -> tuple[int | None, bool]:
    """Converte valores inteiros não negativos, rejeitando contagens fracionárias, negativas ou não finitas."""
    parsed_number, is_bad = parse_numeric(val)
    if is_bad:
        return None, True
    if parsed_number is None:
        return None, False
    if parsed_number < 0 or not parsed_number.is_integer():
        return None, True
    return int(parsed_number), False


def rows_have_equal_values(row_first: dict[str, Any], row_second: dict[str, Any]) -> bool:
    """Verifica se duas observações com a mesma chave possuem valores exatamente idênticos, sem tolerância."""
    for col in ("quota", "nav", "total_assets", "inflow", "outflow", "shareholders"):
        val_first = row_first.get(col)
        val_second = row_second.get(col)
        if val_first is None and val_second is None:
            continue
        if val_first is None or val_second is None:
            return False
        if val_first != val_second:
            return False
    return True


def parse_cvm_records(
    stream: TextIO,
    source_url: str = "local",
    file_hash: str = "",
) -> tuple[dict[tuple[str, str], dict[str, Any]], set[tuple[str, str, str]], dict[str, Any]]:
    """
    Realiza o parse e a validação do fluxo CSV de informes diários da CVM.
    Garante atomicidade na detecção de duplicatas conflitantes e integridade de mês único.
    """
    reader = csv.reader(stream, delimiter=";")
    header = None
    for candidate_row in reader:
        if candidate_row and any(field.strip() for field in candidate_row):
            header = candidate_row
            break
    if header is None:
        raise ValueError("O arquivo CSV informado está vazio.")

    header_clean = [col.lstrip("\ufeff").strip().upper() for col in header]

    if len(header_clean) != len(set(header_clean)):
        raise ValueError("Cabeçalho CSV malformado: contém colunas duplicadas.")

    col_cnpj = -1
    for alias in ("CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO"):
        if alias in header_clean:
            col_cnpj = header_clean.index(alias)
            break

    col_subclass = header_clean.index("ID_SUBCLASSE") if "ID_SUBCLASSE" in header_clean else -1
    col_date = header_clean.index("DT_COMPTC") if "DT_COMPTC" in header_clean else -1
    col_quota = header_clean.index("VL_QUOTA") if "VL_QUOTA" in header_clean else -1
    col_nav = header_clean.index("VL_PATRIM_LIQ") if "VL_PATRIM_LIQ" in header_clean else -1
    col_total = header_clean.index("VL_TOTAL") if "VL_TOTAL" in header_clean else -1
    col_inflow = header_clean.index("CAPTC_DIA") if "CAPTC_DIA" in header_clean else -1
    col_outflow = header_clean.index("RESG_DIA") if "RESG_DIA" in header_clean else -1
    col_shareholders = header_clean.index("NR_COTST") if "NR_COTST" in header_clean else -1

    if col_cnpj == -1 or col_date == -1:
        raise ValueError(
            "Colunas obrigatórias da CVM (CNPJ e DT_COMPTC) não foram encontradas no cabeçalho."
        )

    total_rows = 0
    rejected_rows = 0
    duplicate_rows = 0
    bad_fields_count = 0

    validated_obs: dict[tuple[str, str], dict[str, Any]] = {}
    funds_directory: set[tuple[str, str, str]] = set()

    for row in reader:
        if not row or not any(field.strip() for field in row):
            continue

        row_clean = [col.lstrip("\ufeff").strip().upper() for col in row]
        if row_clean == header_clean or (
            col_cnpj < len(row)
            and row_clean[col_cnpj] in ("CNPJ_FUNDO", "CNPJ_FUNDO_CLASSE")
            and col_date < len(row)
            and row_clean[col_date] == "DT_COMPTC"
        ):
            continue

        total_rows += 1

        if len(row) != len(header_clean):
            rejected_rows += 1
            continue

        cnpj_raw = row[col_cnpj] if col_cnpj < len(row) else None
        cnpj = parse_cnpj(cnpj_raw)
        if not cnpj:
            rejected_rows += 1
            continue

        date_raw = row[col_date] if col_date < len(row) else None
        date_str = parse_date(date_raw)
        if not date_str:
            rejected_rows += 1
            continue

        subclass_raw = (
            row[col_subclass] if (col_subclass != -1 and col_subclass < len(row)) else None
        )
        subclass = parse_subclass(subclass_raw)
        fund_id = f"{cnpj}:{subclass}"

        quota, bad_q = parse_numeric(
            row[col_quota] if col_quota != -1 and col_quota < len(row) else None
        )
        nav, bad_nav = parse_numeric(
            row[col_nav] if col_nav != -1 and col_nav < len(row) else None
        )
        total_assets, bad_tot = parse_numeric(
            row[col_total] if col_total != -1 and col_total < len(row) else None
        )
        inflow, bad_inf = parse_numeric(
            row[col_inflow] if col_inflow != -1 and col_inflow < len(row) else None
        )
        outflow, bad_outf = parse_numeric(
            row[col_outflow] if col_outflow != -1 and col_outflow < len(row) else None
        )
        shareholders, bad_sh = parse_integer(
            row[col_shareholders] if col_shareholders != -1 and col_shareholders < len(row) else None
        )

        bad_fields_count += sum([bad_q, bad_nav, bad_tot, bad_inf, bad_outf, bad_sh])

        obs_row = {
            "fund_id": fund_id,
            "cnpj": cnpj,
            "subclass": subclass,
            "date": date_str,
            "quota": quota,
            "nav": nav,
            "total_assets": total_assets,
            "inflow": inflow,
            "outflow": outflow,
            "shareholders": shareholders,
        }

        key = (fund_id, date_str)
        if key in validated_obs:
            existing = validated_obs[key]
            if rows_have_equal_values(existing, obs_row):
                duplicate_rows += 1
                continue
            else:
                raise ValueError(
                    f"Conflito de dados para a chave ({fund_id}, {date_str}): valores duplicados divergentes encontrados no arquivo."
                )

        validated_obs[key] = obs_row
        funds_directory.add((fund_id, cnpj, subclass))

    if not validated_obs:
        raise ValueError("Nenhum registro válido pôde ser processado a partir do arquivo CSV.")

    months_present = {key[1][:7] for key in validated_obs.keys()}
    if len(months_present) > 1:
        meses_fmt = ", ".join(sorted(months_present))
        raise ValueError(
            f"Arquivo CSV contém múltiplos meses ({meses_fmt}). A importação requer exatamente um único mês por arquivo para garantir atomicidade de substituição."
        )

    affected_month = next(iter(months_present))
    sanitized_url = sanitize_source_url(source_url)
    imported_at = datetime.now(timezone.utc).isoformat()

    audit = {
        "source_url": sanitized_url,
        "file_hash": file_hash,
        "affected_month": affected_month,
        "total_rows": total_rows,
        "valid_rows": len(validated_obs),
        "rejected_rows": rejected_rows,
        "duplicate_rows": duplicate_rows,
        "bad_fields_count": bad_fields_count,
        "imported_at": imported_at,
    }

    return validated_obs, funds_directory, audit


def compute_file_hash_and_decode(file_path: Path | str) -> tuple[str, str]:
    """Calcula o hash SHA-256 e identifica se a codificação do arquivo é UTF-8 ou Latin-1."""
    path = Path(file_path)
    hasher = hashlib.sha256()
    with open(path, "rb") as input_file:
        while chunk := input_file.read(65536):
            hasher.update(chunk)
    file_hash = hasher.hexdigest()

    try:
        with open(path, "rb") as input_file:
            sample = input_file.read(16384)
        if sample.startswith(b"\xef\xbb\xbf"):
            encoding = "utf-8-sig"
        else:
            sample.decode("utf-8")
            encoding = "utf-8"
    except UnicodeDecodeError:
        encoding = "latin1"

    return file_hash, encoding
