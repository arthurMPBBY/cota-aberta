"""A CLI deve manter demonstração e dados públicos em bancos distintos."""

from pathlib import Path
import shutil
import sys

from cota_aberta.cli import main
from cota_aberta.storage import FundStore


def test_demo_command_does_not_seed_real_database(tmp_path, monkeypatch):
    original = Path(__file__).parents[1] / "data/demo/inf_diario_demo.csv"
    target = tmp_path / "data/demo/inf_diario_demo.csv"
    target.parent.mkdir(parents=True)
    shutil.copyfile(original, target)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["cota-aberta", "demo"])
    main()
    assert (tmp_path / "data/demo.sqlite").exists()
    assert not (tmp_path / "data/funds.sqlite").exists()
    assert len(FundStore(tmp_path / "data/demo.sqlite").list_funds()) == 3


def test_import_csv_command_with_expected_month(tmp_path, monkeypatch):
    sample_csv = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "12.345.678/0001-95;2024-01-02;1000000;10.50;990000;500;0;10\n"
    )
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text(sample_csv, encoding="utf-8")
    db_file = tmp_path / "funds_cli.sqlite"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cota-aberta",
            "import-csv",
            str(csv_file),
            "--db",
            str(db_file),
            "--month",
            "2024-01",
        ],
    )
    main()
    assert db_file.exists()
    store = FundStore(db_file)
    assert len(store.list_funds()) == 1
