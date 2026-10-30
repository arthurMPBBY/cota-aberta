"""Módulo de download e extração segura em memória de informes diários da CVM."""

import re
import uuid
import zipfile
from pathlib import Path

import requests

CVM_BASE_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS"
MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE_BYTES = 512 * 1024 * 1024


def validate_month_format(month: str) -> str:
    """Valida se o formato do mês é YYYY-MM e retorna o identificador YYYYMM."""
    clean = month.strip()
    match = re.match(r"^(\d{4})-(0[1-9]|1[0-2])$", clean)
    if not match:
        raise ValueError(
            f"Formato de mês inválido: '{month}'. Utilize o formato YYYY-MM (ex: 2024-01)."
        )
    year = int(match.group(1))
    if year < 2000 or year > 2100:
        raise ValueError(f"Ano fora da faixa suportada pela CVM: {year}.")
    return f"{match.group(1)}{match.group(2)}"


def download_cvm_month(
    month: str,
    output_dir: Path | str = "data/raw",
    refresh: bool = False,
    timeout: int = 60,
    max_size_bytes: int = MAX_FILE_SIZE_BYTES,
) -> tuple[Path, str]:
    """
    Baixa o arquivo compactado de informes diários da CVM para o mês informado.
    Salva o arquivo em cache em data/raw e valida sua integridade ZIP.
    Retorna o caminho do arquivo ZIP baixado e a URL de origem.
    """
    yyyymm = validate_month_format(month)
    url = f"{CVM_BASE_URL}/inf_diario_fi_{yyyymm}.zip"

    dest_dir = Path(output_dir).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / f"inf_diario_fi_{yyyymm}.zip"

    if zip_path.exists() and not refresh:
        cache_is_valid = False
        if zipfile.is_zipfile(zip_path):
            try:
                with zipfile.ZipFile(zip_path, "r") as cached_archive:
                    total_uncompressed = sum(
                        info.file_size for info in cached_archive.infolist()
                    )
                    if total_uncompressed <= MAX_UNCOMPRESSED_SIZE_BYTES:
                        cache_is_valid = cached_archive.testzip() is None
            except Exception:
                cache_is_valid = False
        if cache_is_valid:
            return zip_path, url
        zip_path.unlink(missing_ok=True)

    temp_path = dest_dir / f"inf_diario_fi_{yyyymm}_{uuid.uuid4().hex}.tmp"

    try:
        with requests.get(url, stream=True, timeout=timeout) as response:
            if response.status_code == 404:
                raise FileNotFoundError(
                    f"Arquivo da CVM não encontrado para o mês {month} na URL: {url} (HTTP 404)."
                )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Falha ao realizar download da CVM (HTTP {response.status_code}) para o mês {month}."
                )

            downloaded_bytes = 0
            with open(temp_path, "wb") as output_file:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        downloaded_bytes += len(chunk)
                        if downloaded_bytes > max_size_bytes:
                            raise ValueError(
                                f"O arquivo baixado excedeu o limite máximo seguro de {max_size_bytes // (1024 * 1024)} MB."
                            )
                        output_file.write(chunk)

        if not zipfile.is_zipfile(temp_path):
            raise ValueError(f"O arquivo recebido para o mês {month} não é um arquivo ZIP válido.")

        with zipfile.ZipFile(temp_path, "r") as downloaded_archive:
            total_uncompressed = sum(info.file_size for info in downloaded_archive.infolist())
            if total_uncompressed > MAX_UNCOMPRESSED_SIZE_BYTES:
                raise ValueError(
                    f"O tamanho descompactado do arquivo ZIP excede o limite seguro de {MAX_UNCOMPRESSED_SIZE_BYTES // (1024 * 1024)} MB."
                )
            corrupt = downloaded_archive.testzip()
            if corrupt is not None:
                raise ValueError(f"O arquivo ZIP recebido para o mês {month} está corrompido.")

        temp_path.replace(zip_path)
        return zip_path, url

    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
