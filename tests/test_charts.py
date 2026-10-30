"""Os gráficos não podem disfarçar informes ausentes com linhas contínuas."""

import datetime
from pathlib import Path
import runpy

import pandas as pd
import pytest


@pytest.fixture(scope="module")
def ui_helpers():
    return runpy.run_path(str(Path(__file__).parents[1] / "app.py"), run_name="cota_ui_test")


def test_missing_weekday_breaks_chart_not_raw_observations(ui_helpers):
    raw = pd.DataFrame({
        "date": pd.to_datetime(["2025-06-02", "2025-06-04"]),
        "normalized": [100.0, 102.0],
    })
    figure = ui_helpers["build_quota_chart"](raw)
    assert len(raw) == 2
    assert len(figure.data[0].x) == 3
    assert pd.isna(figure.data[0].y[1])
    assert figure.data[0].connectgaps is False


def test_integer_format_and_datetime_coercion(ui_helpers):
    assert ui_helpers["format_number_br"](1234.0, 0) == "1.234"
    assert ui_helpers["parse_date_safe"](
        pd.Timestamp("2025-06-02"), datetime.date(2000, 1, 1)
    ) == datetime.date(2025, 6, 2)
