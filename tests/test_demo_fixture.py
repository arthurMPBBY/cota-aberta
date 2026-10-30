"""A demonstração deve exercitar transparência, não fingir dados de mercado."""

from pathlib import Path

from cota_aberta.analytics import analyze_period
from cota_aberta.storage import FundStore


def test_demo_preserves_subclasses_and_intentional_gaps(tmp_path):
    fixture = Path(__file__).parents[1] / "data/demo/inf_diario_demo.csv"
    store = FundStore(tmp_path / "demo.sqlite")
    audit = store.import_csv(fixture, source_url="synthetic-demo")
    assert audit["valid_rows"] == 62
    assert audit["rejected_rows"] == 0
    funds = store.list_funds()
    assert len(funds) == 3
    assert len({fund["cnpj"] for fund in funds}) == 2
    observations = store.read_observations("00000000000100:1001", "2025-06-01", "2025-06-30")
    result = analyze_period(observations, "2025-06-01", "2025-06-30")
    assert result["metrics"]["observations"] == 20
    assert result["metrics"]["invalid_quotas"] == 1
    assert result["metrics"]["missing_weekdays"] == 1
    assert result["metrics"]["flow_missing_days"] >= 1
    assert result["metrics"]["return_pct"] is not None
    codes = {item["code"] for item in result["quality"]}
    assert "INVALID_QUOTAS" in codes
    assert "MISSING_WEEKDAYS" in codes
    assert "PARTIAL_FLOWS" in codes
