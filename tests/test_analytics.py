"""Testes unitários para cálculos de rentabilidade, fluxos e diagnósticos de qualidade."""

import numpy as np
import pandas as pd
import pytest

from cota_aberta.analytics import analyze_period


def test_essential_return_calculation():
    """Valida o cálculo exato de retorno: 100 -> 110 -> 99 = -1.0%."""
    data = {
        "date": ["2024-01-02", "2024-01-03", "2024-01-04"],
        "quota": [100.0, 110.0, 99.0],
        "nav": [1000.0, 1100.0, 990.0],
        "total_assets": [1000.0, 1100.0, 990.0],
        "inflow": [10.0, 0.0, 0.0],
        "outflow": [0.0, 0.0, 20.0],
        "shareholders": [5, 5, 4],
    }
    df = pd.DataFrame(data)
    result = analyze_period(df, start="2024-01-02", end="2024-01-04")

    metrics = result["metrics"]
    assert metrics["return_pct"] == pytest.approx(-1.0, rel=1e-7)
    assert metrics["start_date"] == "2024-01-02"
    assert metrics["end_date"] == "2024-01-04"
    assert metrics["start_quota"] == 100.0
    assert metrics["end_quota"] == 99.0
    assert metrics["nav"] == 990.0
    assert metrics["shareholders"] == 4
    assert metrics["inflow"] == 10.0
    assert metrics["outflow"] == 20.0
    assert metrics["net_flow"] == -10.0
    assert metrics["observations"] == 3

    series = result["series"]
    assert list(series["normalized"]) == pytest.approx([100.0, 110.0, 99.0])


def test_insufficient_or_single_point_or_no_valid_quotas():
    """Valida que menos de duas cotas válidas retornam return_pct None."""
    df_one = pd.DataFrame({
        "date": ["2024-01-02"],
        "quota": [100.0],
        "nav": [1000.0],
        "total_assets": [1000.0],
        "inflow": [0.0],
        "outflow": [0.0],
        "shareholders": [1],
    })
    res_one = analyze_period(df_one, start="2024-01-02", end="2024-01-05")
    assert res_one["metrics"]["return_pct"] is None
    assert any(quality_item["code"] == "INSUFFICIENT_DATA" for quality_item in res_one["quality"])

    df_none = pd.DataFrame({
        "date": ["2024-01-02", "2024-01-03"],
        "quota": [None, -5.0],
        "nav": [1000.0, 1000.0],
        "total_assets": [1000.0, 1000.0],
        "inflow": [0.0, 0.0],
        "outflow": [0.0, 0.0],
        "shareholders": [1, 1],
    })
    res_none = analyze_period(df_none, start="2024-01-02", end="2024-01-03")
    assert res_none["metrics"]["return_pct"] is None
    assert res_none["metrics"]["invalid_quotas"] == 2
    assert any(quality_item["code"] == "INVALID_QUOTAS" for quality_item in res_none["quality"])


def test_nonfinite_quotas_and_base100_retention():
    """Valida que observações com cotas não finitas são retidas na série mas normalizadas como NaN."""
    df = pd.DataFrame({
        "date": ["2024-01-02", "2024-01-03", "2024-01-04"],
        "quota": [100.0, np.nan, 105.0],
        "nav": [1000.0, 1020.0, 1050.0],
        "total_assets": [1000.0, 1020.0, 1050.0],
        "inflow": [0.0, 0.0, 0.0],
        "outflow": [0.0, 0.0, 0.0],
        "shareholders": [2, 2, 2],
    })
    res = analyze_period(df, start="2024-01-02", end="2024-01-04")
    assert res["metrics"]["return_pct"] == pytest.approx(5.0)
    assert res["metrics"]["invalid_quotas"] == 1

    series = res["series"]
    assert len(series) == 3
    assert series.iloc[0]["normalized"] == 100.0
    assert pd.isna(series.iloc[1]["normalized"])
    assert series.iloc[2]["normalized"] == 105.0


def test_boundary_clipping_diagnostics():
    """Garante emissão de alertas quando o intervalo solicitado ultrapassa as datas com cotas válidas."""
    df = pd.DataFrame({
        "date": ["2024-01-10", "2024-01-15"],
        "quota": [50.0, 55.0],
        "nav": [500.0, 550.0],
        "total_assets": [500.0, 550.0],
        "inflow": [0.0, 0.0],
        "outflow": [0.0, 0.0],
        "shareholders": [1, 1],
    })
    res = analyze_period(df, start="2024-01-01", end="2024-01-31")
    codes = [quality_item["code"] for quality_item in res["quality"]]
    assert "CLIPPED_START" in codes
    assert "CLIPPED_END" in codes
    assert "MISSING_WEEKDAYS" in codes


def test_no_zero_filling_flows_and_partial_flow_warning():
    """Garante que fluxos ausentes não sejam preenchidos com zero e que net_flow seja nulo quando um lado for todo nulo."""
    df_missing_flow = pd.DataFrame({
        "date": ["2024-01-02", "2024-01-03"],
        "quota": [10.0, 11.0],
        "nav": [100.0, 110.0],
        "total_assets": [100.0, 110.0],
        "inflow": [None, None],
        "outflow": [5.0, 10.0],
        "shareholders": [2, 2],
    })
    res = analyze_period(df_missing_flow, start="2024-01-02", end="2024-01-03")
    assert res["metrics"]["inflow"] is None
    assert res["metrics"]["outflow"] == 15.0
    assert res["metrics"]["net_flow"] is None
    assert res["metrics"]["flow_missing_days"] == 2
    assert any(quality_item["code"] == "PARTIAL_FLOWS" for quality_item in res["quality"])


def test_nonfinite_flows_treated_as_missing_not_infinity():
    """Garante que fluxos não finitos (inf, -inf) sejam tratados como ausentes, sem gerar soma infinita."""
    df = pd.DataFrame({
        "date": ["2024-01-02", "2024-01-03"],
        "quota": [10.0, 11.0],
        "nav": [100.0, 110.0],
        "total_assets": [100.0, 110.0],
        "inflow": [np.inf, 10.0],
        "outflow": [-np.inf, 5.0],
        "shareholders": [2, 2],
    })
    res = analyze_period(df, start="2024-01-02", end="2024-01-03")
    assert res["metrics"]["inflow"] == 10.0
    assert res["metrics"]["outflow"] == 5.0
    assert res["metrics"]["net_flow"] == 5.0
    assert res["metrics"]["flow_missing_days"] == 1
    assert any(quality_item["code"] == "PARTIAL_FLOWS" for quality_item in res["quality"])


def test_all_missing_flows_triggers_quality_flag():
    """Garante que fluxos totalmente ausentes gerem flag de qualidade MISSING_FLOWS."""
    df = pd.DataFrame({
        "date": ["2024-01-02", "2024-01-03"],
        "quota": [10.0, 11.0],
        "nav": [100.0, 110.0],
        "total_assets": [100.0, 110.0],
        "inflow": [None, None],
        "outflow": [None, None],
        "shareholders": [2, 2],
    })
    res = analyze_period(df, start="2024-01-02", end="2024-01-03")
    assert res["metrics"]["inflow"] is None
    assert res["metrics"]["outflow"] is None
    assert res["metrics"]["net_flow"] is None
    assert any(quality_item["code"] == "MISSING_FLOWS" for quality_item in res["quality"])


def test_missing_weekdays_makes_flows_partial_even_when_all_rows_have_flows():
    """Garante que lacunas de dias úteis marquem os fluxos acumulados como parciais."""
    df = pd.DataFrame({
        "date": ["2024-01-02", "2024-01-05"],
        "quota": [10.0, 11.0],
        "nav": [100.0, 110.0],
        "total_assets": [100.0, 110.0],
        "inflow": [5.0, 5.0],
        "outflow": [2.0, 2.0],
        "shareholders": [2, 2],
    })
    res = analyze_period(df, start="2024-01-01", end="2024-01-05")
    assert any(
        quality_item["code"] == "PARTIAL_FLOWS" and "feriados nacionais" in quality_item["message"]
        for quality_item in res["quality"]
    )


def test_duplicate_dates_rejected_with_value_error():
    """Garante que observações com datas duplicadas no intervalo sejam rejeitadas com erro."""
    df = pd.DataFrame({
        "date": ["2024-01-02", "2024-01-02"],
        "quota": [10.0, 10.0],
        "nav": [100.0, 100.0],
        "total_assets": [1000.0, 100.0],
        "inflow": [0.0, 0.0],
        "outflow": [0.0, 0.0],
        "shareholders": [1, 1],
    })
    with pytest.raises(ValueError, match="datas duplicadas"):
        analyze_period(df, start="2024-01-01", end="2024-01-05")


def test_empty_frame_and_zero_observations_preserve_consistent_metrics():
    """Garante métricas e tipos consistentes tanto para DataFrame vazio quanto para filtro sem resultados."""
    empty_df = pd.DataFrame()
    res_empty = analyze_period(empty_df, start="2024-01-01", end="2024-01-05")
    assert res_empty["metrics"]["observations"] == 0
    assert res_empty["metrics"]["return_pct"] is None
    assert res_empty["series"].empty
    assert list(res_empty["series"].columns) == [
        "date", "quota", "nav", "total_assets", "inflow", "outflow", "shareholders", "normalized"
    ]

    filtered_out_df = pd.DataFrame({
        "date": ["2024-02-01"],
        "quota": [10.0],
        "nav": [100.0],
        "total_assets": [100.0],
        "inflow": [0.0],
        "outflow": [0.0],
        "shareholders": [1],
    })
    res_filtered = analyze_period(filtered_out_df, start="2024-01-01", end="2024-01-05")
    assert res_filtered["metrics"]["observations"] == 0
    assert res_filtered["metrics"]["return_pct"] is None
    assert res_filtered["series"].empty
    assert list(res_filtered["series"].columns) == [
        "date", "quota", "nav", "total_assets", "inflow", "outflow", "shareholders", "normalized"
    ]


def test_missing_final_nav_and_shareholders_warnings():
    """Garante diagnósticos de alerta quando nav ou cotistas estiverem ausentes no último dia."""
    df = pd.DataFrame({
        "date": ["2024-01-02", "2024-01-03"],
        "quota": [10.0, 11.0],
        "nav": [100.0, None],
        "total_assets": [100.0, 110.0],
        "inflow": [0.0, 0.0],
        "outflow": [0.0, 0.0],
        "shareholders": [1, None],
    })
    res = analyze_period(df, start="2024-01-02", end="2024-01-03")
    assert res["metrics"]["nav"] is None
    assert res["metrics"]["shareholders"] is None
    codes = [quality_item["code"] for quality_item in res["quality"]]
    assert "MISSING_FINAL_NAV" in codes
    assert "MISSING_FINAL_SHAREHOLDERS" in codes


def test_nonfinite_shareholders_does_not_throw():
    """Garante que cotistas não finitos ou inválidos não levantem exceção de conversão."""
    df = pd.DataFrame({
        "date": ["2024-01-02"],
        "quota": [10.0],
        "nav": [100.0],
        "total_assets": [100.0],
        "inflow": [0.0],
        "outflow": [0.0],
        "shareholders": [float("inf")],
    })
    res = analyze_period(df, start="2024-01-02", end="2024-01-02")
    assert res["metrics"]["shareholders"] is None


def test_dataframe_missing_optional_columns_handled_gracefully():
    """Garante que DataFrames com apenas data e cota não gerem KeyError e preencham métricas e colunas."""
    minimal_df = pd.DataFrame({
        "date": ["2024-01-02", "2024-01-03"],
        "quota": [10.0, 12.0],
    })
    res = analyze_period(minimal_df, start="2024-01-02", end="2024-01-03")
    assert res["metrics"]["return_pct"] == pytest.approx(20.0)
    assert res["metrics"]["inflow"] is None
    assert res["metrics"]["outflow"] is None
    assert res["metrics"]["nav"] is None
    assert res["metrics"]["shareholders"] is None
    codes = [quality_item["code"] for quality_item in res["quality"]]
    assert "MISSING_FLOWS" in codes
    assert "MISSING_FINAL_NAV" in codes
    assert "MISSING_FINAL_SHAREHOLDERS" in codes
    assert list(res["series"].columns) == [
        "date", "quota", "nav", "total_assets", "inflow", "outflow", "shareholders", "normalized"
    ]
