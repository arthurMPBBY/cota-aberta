"""Testes unitários e de integração para a camada de persistência SQLite (FundStore)."""

import sqlite3
import zipfile
import pandas as pd
import pytest

from cota_aberta.storage import FundStore


@pytest.fixture
def store(tmp_path):
    """Cria uma instância temporária de FundStore."""
    db_file = tmp_path / "test_funds.sqlite"
    store_inst = FundStore(db_file)
    store_inst.initialize()
    return store_inst


def test_initialization_and_empty_queries(store):
    """Garante que um banco recém-inicializado responda com coleções vazias válidas."""
    funds = store.list_funds()
    assert funds == []

    obs = store.read_observations("qualquer_id")
    assert isinstance(obs, pd.DataFrame)
    assert obs.empty
    expected_cols = [
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
    assert list(obs.columns) == expected_cols
    assert pd.api.types.is_datetime64_any_dtype(obs["date"])

    history = store.import_history()
    assert history == []


def test_import_and_idempotency(store, tmp_path):
    """Valida a importação de CSV e garante que reimportações do mesmo mês sejam idempotentes."""
    csv_content = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "12.345.678/0001-95;2024-01-02;1000000;10.50;990000;500;0;10\n"
        "12.345.678/0001-95;2024-01-03;1002000;10.52;992000;0;100;10\n"
    )
    csv_file = tmp_path / "inf_diario_fi_202401.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    audit1 = store.import_csv(csv_file, source_url="https://dados.cvm.gov.br/arquivo.zip")
    assert audit1["valid_rows"] == 2
    assert audit1["affected_month"] == "2024-01"

    funds = store.list_funds()
    assert len(funds) == 1
    assert funds[0]["fund_id"] == "12345678000195:"
    assert funds[0]["observations"] == 2
    assert funds[0]["first_date"] == "2024-01-02"
    assert funds[0]["last_date"] == "2024-01-03"

    audit2 = store.import_csv(csv_file, source_url="local")
    assert audit2["valid_rows"] == 2

    funds_after = store.list_funds()
    assert len(funds_after) == 1
    assert funds_after[0]["observations"] == 2

    obs_df = store.read_observations("12345678000195:")
    assert len(obs_df) == 2


def test_subclasses_preservation(store, tmp_path):
    """Garante que diferentes subclasses do mesmo CNPJ sejam mantidas como identidades separadas."""
    csv_content = (
        "CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "12.345.678/0001-95;;2024-01-02;500000;10.0;500000;0;0;5\n"
        "12.345.678/0001-95;0;2024-01-02;200000;20.0;200000;0;0;2\n"
        "12.345.678/0001-95;CLASSE_B;2024-01-02;300000;30.0;300000;0;0;3\n"
    )
    csv_file = tmp_path / "subclasses.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    audit = store.import_csv(csv_file)
    assert audit["valid_rows"] == 3

    funds = store.list_funds()
    fund_ids = {fund_record["fund_id"] for fund_record in funds}
    expected_ids = {"12345678000195:", "12345678000195:0", "12345678000195:CLASSE_B"}
    assert fund_ids == expected_ids


def test_atomic_failure_and_rollback_on_conflict(store, tmp_path):
    """Garante que falhas de validação (conflito ou multi-mês) não afetem o banco de dados pré-existente."""
    initial_csv = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "12.345.678/0001-95;2024-01-02;1000000;10.0;1000000;0;0;1\n"
    )
    file_initial = tmp_path / "valid.csv"
    file_initial.write_text(initial_csv, encoding="utf-8")
    store.import_csv(file_initial)

    assert len(store.list_funds()) == 1

    conflicting_csv = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "12.345.678/0001-95;2024-01-03;1000000;10.0;1000000;0;0;1\n"
        "12.345.678/0001-95;2024-01-03;1000000;15.0;1000000;0;0;1\n"
    )
    file_bad = tmp_path / "conflicting.csv"
    file_bad.write_text(conflicting_csv, encoding="utf-8")

    with pytest.raises(ValueError, match="Conflito de dados para a chave"):
        store.import_csv(file_bad)

    obs = store.read_observations("12345678000195:")
    assert len(obs) == 1
    assert float(obs.iloc[0]["quota"]) == 10.0


def test_rejected_rows_blocks_import_and_preserves_db(store, tmp_path):
    """Garante que qualquer linha inválida rejeite o lote antes do DELETE e preserve o banco intacto."""
    initial_csv = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "12.345.678/0001-95;2024-01-02;1000000;10.0;1000000;0;0;1\n"
    )
    file_initial = tmp_path / "initial.csv"
    file_initial.write_text(initial_csv, encoding="utf-8")
    store.import_csv(file_initial)

    bad_identity_csv = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "12.345.678/0001-95;2024-01-03;1000000;12.0;1000000;0;0;1\n"
        "abc123;2024-01-03;1000000;12.0;1000000;0;0;1\n"
    )
    file_bad_identity = tmp_path / "bad_identity.csv"
    file_bad_identity.write_text(bad_identity_csv, encoding="utf-8")

    with pytest.raises(ValueError, match="Importação rejeitada"):
        store.import_csv(file_bad_identity)

    obs = store.read_observations("12345678000195:")
    assert len(obs) == 1
    assert float(obs.iloc[0]["quota"]) == 10.0


def test_import_zip_file_directly(store, tmp_path):
    """Valida a importação direta de arquivos .zip sem extração em disco (proteção Zip Slip)."""
    csv_bytes = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "12.345.678/0001-95;2024-01-02;1000000;10.50;990000;0;0;10\n"
    ).encode("latin1")

    zip_file = tmp_path / "inf_diario_fi_202401.zip"
    with zipfile.ZipFile(zip_file, "w") as zip_archive:
        zip_archive.writestr("inf_diario_fi_202401.csv", csv_bytes)

    audit = store.import_csv(zip_file)
    assert audit["valid_rows"] == 1
    obs = store.read_observations("12345678000195:")
    assert len(obs) == 1
    assert float(obs.iloc[0]["quota"]) == 10.50


def test_zip_multiple_csv_members_rejected(store, tmp_path):
    """Garante que arquivos ZIP com múltiplos membros CSV sejam rejeitados por ambiguidade."""
    zip_file = tmp_path / "multi_csv.zip"
    with zipfile.ZipFile(zip_file, "w") as zip_archive:
        zip_archive.writestr("file_one.csv", "CNPJ_FUNDO;DT_COMPTC\n12.345.678/0001-95;2024-01-02\n")
        zip_archive.writestr("file_two.csv", "CNPJ_FUNDO;DT_COMPTC\n12.345.678/0001-95;2024-01-03\n")

    with pytest.raises(ValueError, match="Arquivo ZIP ambíguo"):
        store.import_csv(zip_file)


def test_zip_uncompressed_size_cap_rejected(store, tmp_path, monkeypatch):
    """Garante que arquivos ZIP com tamanho descompactado excedendo o teto sejam rejeitados."""
    zip_file = tmp_path / "oversize.zip"
    with zipfile.ZipFile(zip_file, "w") as zip_archive:
        zip_archive.writestr("test.csv", "CNPJ_FUNDO;DT_COMPTC\n")

    monkeypatch.setattr("cota_aberta.storage.MAX_UNCOMPRESSED_SIZE_BYTES", 10)
    with pytest.raises(ValueError, match="excede o limite de segurança"):
        store.import_csv(zip_file)


def test_list_funds_excludes_orphan_records_with_zero_observations(store):
    """Garante que fundos sem observações (órfãos) não sejam retornados por list_funds."""
    with sqlite3.connect(store.path) as conn:
        conn.execute(
            "INSERT INTO funds (fund_id, cnpj, subclass, name, created_at) VALUES (?, ?, ?, ?, ?)",
            ("99999999000199:", "99999999000199", "", "Fundo Órfão", "2024-01-01T00:00:00Z"),
        )
    funds = store.list_funds()
    assert len(funds) == 0


def test_expected_month_mismatch_rejected(store, tmp_path):
    """Garante que divergência entre o mês solicitado e o mês contido no arquivo aborte a importação."""
    csv_content = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "12.345.678/0001-95;2024-01-02;1000000;10.50;990000;500;0;10\n"
    )
    csv_file = tmp_path / "inf_diario_fi_202401.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    with pytest.raises(ValueError, match="Mês de competência divergente"):
        store.import_csv(csv_file, expected_month="2024-02")


def test_expected_month_format_without_hyphen_accepted(store, tmp_path):
    """Garante que o mês esperado informado no formato YYYYMM seja aceito para YYYY-MM."""
    csv_content = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "12.345.678/0001-95;2024-01-02;1000000;10.50;990000;500;0;10\n"
    )
    csv_file = tmp_path / "inf_diario_fi_202401.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    audit = store.import_csv(csv_file, expected_month="202401")
    assert audit["affected_month"] == "2024-01"


def test_read_observations_dirty_shareholders_floats_handled_safely(store):
    """Garante que valores não inteiros em cotistas no banco não causem erro de conversão."""
    store.initialize()
    with sqlite3.connect(store.path) as conn:
        conn.execute(
            "INSERT INTO funds (fund_id, cnpj, subclass, name, created_at) VALUES (?, ?, ?, ?, ?)",
            ("12345678000195:", "12345678000195", "", "Fundo Teste", "2024-01-01T00:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO observations (fund_id, date, quota, nav, total_assets, inflow, outflow, shareholders, source_url, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("12345678000195:", "2024-01-02", 10.0, 100.0, 100.0, 0.0, 0.0, 15.5, "local", "2024-01-02T00:00:00Z"),
        )

    observations = store.read_observations("12345678000195:")
    assert len(observations) == 1
    assert pd.isna(observations.iloc[0]["shareholders"])
