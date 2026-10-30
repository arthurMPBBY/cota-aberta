"""Módulo de persistência e repositório SQLite para cotas e dados cadastrais de fundos."""

import hashlib
import io
import sqlite3
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cota_aberta.ingestion import compute_file_hash_and_decode, parse_cvm_records

MAX_UNCOMPRESSED_SIZE_BYTES = 512 * 1024 * 1024


class FundStore:
    """Repositório de armazenamento SQLite para cotas diárias de fundos de investimento."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()

    def initialize(self) -> None:
        """Cria o esquema do banco de dados caso ainda não exista."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS funds (
                    fund_id TEXT PRIMARY KEY,
                    cnpj TEXT NOT NULL,
                    subclass TEXT NOT NULL,
                    name TEXT,
                    created_at TEXT NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS observations (
                    fund_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    quota REAL,
                    nav REAL,
                    total_assets REAL,
                    inflow REAL,
                    outflow REAL,
                    shareholders INTEGER,
                    source_url TEXT,
                    imported_at TEXT NOT NULL,
                    PRIMARY KEY (fund_id, date),
                    FOREIGN KEY (fund_id) REFERENCES funds(fund_id) ON DELETE CASCADE
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_observations_date ON observations(date);")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_observations_fund_date ON observations(fund_id, date);"
            )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS import_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_url TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    affected_month TEXT NOT NULL,
                    total_rows INTEGER NOT NULL,
                    valid_rows INTEGER NOT NULL,
                    rejected_rows INTEGER NOT NULL,
                    duplicate_rows INTEGER NOT NULL,
                    bad_fields_count INTEGER NOT NULL,
                    imported_at TEXT NOT NULL
                );
            """)

    def import_csv(
        self,
        path: str | Path,
        source_url: str = "local",
        expected_month: str | None = None,
    ) -> dict[str, Any]:
        """
        Importa um arquivo CSV ou ZIP de informe diário da CVM.
        Garante a substituição atômica e transacional do mês afetado apenas após validação integral.
        """
        self.initialize()
        file_path = Path(path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

        if file_path.suffix.lower() == ".zip":
            hasher = hashlib.sha256()
            with open(file_path, "rb") as binary_file:
                while chunk := binary_file.read(65536):
                    hasher.update(chunk)
            file_hash = hasher.hexdigest()

            with zipfile.ZipFile(file_path, "r") as zip_archive:
                total_uncompressed = sum(info.file_size for info in zip_archive.infolist())
                if total_uncompressed > MAX_UNCOMPRESSED_SIZE_BYTES:
                    raise ValueError(
                        f"Tamanho descompactado do arquivo ZIP ({total_uncompressed / (1024 * 1024):.1f} MB) "
                        f"excede o limite de segurança de {MAX_UNCOMPRESSED_SIZE_BYTES // (1024 * 1024)} MB."
                    )
                corrupt = zip_archive.testzip()
                if corrupt is not None:
                    raise ValueError(f"O arquivo ZIP {file_path.name} está corrompido.")

                csv_members = [
                    member_name
                    for member_name in zip_archive.namelist()
                    if member_name.lower().endswith(".csv")
                ]
                if not csv_members:
                    raise ValueError(
                        f"Nenhum arquivo CSV encontrado dentro do arquivo ZIP {file_path.name}."
                    )
                if len(csv_members) > 1:
                    raise ValueError(
                        f"Arquivo ZIP ambíguo: contém múltiplos arquivos CSV ({', '.join(csv_members)}). "
                        "Esperado exatamente um arquivo CSV."
                    )
                csv_member = csv_members[0]
                with zip_archive.open(csv_member, "r") as raw_stream:
                    sample = raw_stream.read(16384)
                    raw_stream.seek(0)
                    if sample.startswith(b"\xef\xbb\xbf"):
                        encoding = "utf-8-sig"
                    else:
                        try:
                            sample.decode("utf-8")
                            encoding = "utf-8"
                        except UnicodeDecodeError:
                            encoding = "latin1"

                    text_stream = io.TextIOWrapper(raw_stream, encoding=encoding, errors="replace")
                    validated_obs, funds_directory, audit = parse_cvm_records(
                        text_stream,
                        source_url=source_url,
                        file_hash=file_hash,
                    )
        else:
            file_hash, encoding = compute_file_hash_and_decode(file_path)
            with open(file_path, "r", encoding=encoding, errors="replace") as input_file:
                validated_obs, funds_directory, audit = parse_cvm_records(
                    input_file,
                    source_url=source_url,
                    file_hash=file_hash,
                )

        if audit.get("rejected_rows", 0) > 0:
            raise ValueError(
                f"Importação rejeitada: o arquivo contém {audit['rejected_rows']} linha(s) inválida(s) "
                "(identidade, data ou formato corrompido). O banco de dados pré-existente foi preservado."
            )

        affected_month = audit["affected_month"]
        if expected_month is not None:
            expected_clean = expected_month.strip()
            affected_clean = affected_month.strip()
            if (
                expected_clean != affected_clean
                and expected_clean.replace("-", "") != affected_clean.replace("-", "")
            ):
                raise ValueError(
                    f"Mês de competência divergente: o arquivo contém dados de {affected_month}, "
                    f"mas a competência solicitada foi {expected_month}."
                )

        month_start = f"{affected_month}-01"
        month_end = f"{affected_month}-31"
        imported_at = audit["imported_at"]
        clean_url = audit["source_url"]

        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            cursor = conn.cursor()

            funds_rows = [
                (fund_id, cnpj, subclass, imported_at)
                for fund_id, cnpj, subclass in funds_directory
            ]
            cursor.executemany(
                "INSERT OR IGNORE INTO funds (fund_id, cnpj, subclass, name, created_at) VALUES (?, ?, ?, NULL, ?);",
                funds_rows,
            )

            cursor.execute(
                "DELETE FROM observations WHERE date >= ? AND date <= ?;",
                (month_start, month_end),
            )

            obs_rows = [
                (
                    item["fund_id"],
                    item["date"],
                    item["quota"],
                    item["nav"],
                    item["total_assets"],
                    item["inflow"],
                    item["outflow"],
                    item["shareholders"],
                    clean_url,
                    imported_at,
                )
                for item in validated_obs.values()
            ]
            cursor.executemany(
                """
                INSERT INTO observations (
                    fund_id, date, quota, nav, total_assets, inflow, outflow, shareholders, source_url, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                obs_rows,
            )

            cursor.execute(
                """
                INSERT INTO import_history (
                    source_url, file_hash, affected_month, total_rows, valid_rows,
                    rejected_rows, duplicate_rows, bad_fields_count, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    clean_url,
                    audit["file_hash"],
                    audit["affected_month"],
                    audit["total_rows"],
                    audit["valid_rows"],
                    audit["rejected_rows"],
                    audit["duplicate_rows"],
                    audit["bad_fields_count"],
                    audit["imported_at"],
                ),
            )

        return audit

    def list_funds(self, search: str = "") -> list[dict[str, Any]]:
        """Lista os fundos cadastrados com observações, resumo temporal e contagem."""
        self.initialize()
        term = search.strip()
        search_pattern = f"%{term}%" if term else "%"

        query = """
            SELECT
                f.fund_id,
                f.cnpj,
                f.subclass,
                f.name,
                MIN(o.date) AS first_date,
                MAX(o.date) AS last_date,
                COUNT(o.date) AS observations
            FROM funds f
            JOIN observations o ON f.fund_id = o.fund_id
            WHERE (? = '%' OR f.fund_id LIKE ? OR f.cnpj LIKE ? OR (f.name IS NOT NULL AND f.name LIKE ?) OR f.subclass LIKE ?)
            GROUP BY f.fund_id, f.cnpj, f.subclass, f.name
            HAVING COUNT(o.date) > 0
            ORDER BY f.cnpj ASC, f.subclass ASC;
        """

        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                query,
                (
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                ),
            )
            rows = cursor.fetchall()

            return [
                {
                    "fund_id": row["fund_id"],
                    "cnpj": row["cnpj"],
                    "subclass": row["subclass"],
                    "name": row["name"],
                    "first_date": row["first_date"],
                    "last_date": row["last_date"],
                    "observations": row["observations"],
                }
                for row in rows
            ]

    def read_observations(
        self,
        fund_id: str,
        start: str | date | datetime | None = None,
        end: str | date | datetime | None = None,
    ) -> pd.DataFrame:
        """Lê as observações históricas de um fundo em um intervalo, retornando um DataFrame tipado."""
        self.initialize()

        def _format_date(date_value: str | date | datetime | None) -> str | None:
            if date_value is None:
                return None
            if isinstance(date_value, datetime):
                return date_value.strftime("%Y-%m-%d")
            if isinstance(date_value, date):
                return date_value.strftime("%Y-%m-%d")
            date_text = str(date_value).strip()
            return date_text[:10] if len(date_text) >= 10 else date_text

        start_str = _format_date(start)
        end_str = _format_date(end)

        conditions = ["fund_id = ?"]
        params: list[Any] = [fund_id]

        if start_str:
            conditions.append("date >= ?")
            params.append(start_str)
        if end_str:
            conditions.append("date <= ?")
            params.append(end_str)

        query = f"""
            SELECT date, quota, nav, total_assets, inflow, outflow, shareholders, source_url, imported_at
            FROM observations
            WHERE {' AND '.join(conditions)}
            ORDER BY date ASC;
        """

        columns = [
            "date",
            "quota",
            "nav",
            "total_assets",
            "inflow",
            "outflow",
            "shareholders",
            "source_url",
            "imported_at",
        ]

        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        if not rows:
            return pd.DataFrame(
                {
                    "date": pd.to_datetime([]),
                    "quota": pd.Series(dtype="float64"),
                    "nav": pd.Series(dtype="float64"),
                    "total_assets": pd.Series(dtype="float64"),
                    "inflow": pd.Series(dtype="float64"),
                    "outflow": pd.Series(dtype="float64"),
                    "shareholders": pd.Series(dtype="Int64"),
                    "source_url": pd.Series(dtype="object"),
                    "imported_at": pd.Series(dtype="object"),
                }
            )

        data = {col: [row[col] for row in rows] for col in columns}
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        df["quota"] = pd.to_numeric(df["quota"], errors="coerce")
        df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
        df["total_assets"] = pd.to_numeric(df["total_assets"], errors="coerce")
        df["inflow"] = pd.to_numeric(df["inflow"], errors="coerce")
        df["outflow"] = pd.to_numeric(df["outflow"], errors="coerce")

        shareholders_numeric = pd.to_numeric(df["shareholders"], errors="coerce")
        shareholders_valid = shareholders_numeric.where(
            shareholders_numeric.isna()
            | (
                np.isfinite(shareholders_numeric)
                & (shareholders_numeric >= 0)
                & (shareholders_numeric % 1 == 0)
            ),
            other=np.nan,
        )
        df["shareholders"] = pd.Series(shareholders_valid, dtype="Int64")
        return df

    def import_history(self) -> list[dict[str, Any]]:
        """Retorna o histórico de importações realizadas."""
        self.initialize()
        query = """
            SELECT source_url, file_hash, affected_month, total_rows, valid_rows,
                   rejected_rows, duplicate_rows, bad_fields_count, imported_at
            FROM import_history
            ORDER BY id DESC;
        """
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)
            return [dict(record) for record in cursor.fetchall()]
