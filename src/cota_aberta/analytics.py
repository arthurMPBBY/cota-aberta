"""Módulo de cálculo de métricas de rentabilidade, fluxo e avaliação de qualidade de dados."""

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def _to_date_str(val: str | date | datetime) -> str:
    """Converte um valor de data para string no formato ISO YYYY-MM-DD."""
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")
    date_text = str(val).strip()
    return date_text[:10] if len(date_text) >= 10 else date_text


def _clean_flow_value(val: Any) -> float | None:
    """Converte valores de fluxo para float finito, tratando não finitos como ausentes."""
    if val is None or pd.isna(val):
        return None
    try:
        flow_value = float(val)
        return flow_value if math.isfinite(flow_value) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _build_empty_series() -> pd.DataFrame:
    """Gera um DataFrame vazio estruturado e tipado para a série temporal."""
    return pd.DataFrame({
        "date": pd.to_datetime([]),
        "quota": pd.Series(dtype="float64"),
        "nav": pd.Series(dtype="float64"),
        "total_assets": pd.Series(dtype="float64"),
        "inflow": pd.Series(dtype="float64"),
        "outflow": pd.Series(dtype="float64"),
        "shareholders": pd.Series(dtype="Int64"),
        "normalized": pd.Series(dtype="float64"),
    })


def analyze_period(
    frame: pd.DataFrame,
    start: str | date | datetime,
    end: str | date | datetime,
) -> dict[str, Any]:
    """
    Analisa o desempenho e a integridade dos dados de um fundo dentro do período solicitado.
    Retorna um dicionário contendo métricas, diagnósticos de qualidade e a série temporal processada.
    """
    start_str = _to_date_str(start)
    end_str = _to_date_str(end)

    if start_str > end_str:
        raise ValueError(
            f"A data inicial ({start_str}) não pode ser posterior à data final ({end_str})."
        )

    series_cols = [
        "date",
        "quota",
        "nav",
        "total_assets",
        "inflow",
        "outflow",
        "shareholders",
        "normalized",
    ]

    quality: list[dict[str, str]] = []

    if frame.empty or "date" not in frame.columns:
        expected_bdays = pd.bdate_range(start=start_str, end=end_str)
        missing_weekdays = len(expected_bdays)

        quality.append({
            "severity": "warning",
            "code": "NO_DATA",
            "message": f"Nenhuma observação encontrada para o intervalo solicitado ({start_str} a {end_str}).",
        })
        if missing_weekdays > 0:
            quality.append({
                "severity": "warning",
                "code": "MISSING_WEEKDAYS",
                "message": f"Estimativa de {missing_weekdays} dias úteis sem dados no período (estimativa não considera feriados nacionais).",
            })

        metrics = {
            "return_pct": None,
            "start_date": None,
            "end_date": None,
            "start_quota": None,
            "end_quota": None,
            "nav": None,
            "inflow": None,
            "outflow": None,
            "net_flow": None,
            "shareholders": None,
            "observations": 0,
            "missing_weekdays": missing_weekdays,
            "invalid_quotas": 0,
            "flow_missing_days": 0,
        }

        return {
            "metrics": metrics,
            "quality": quality,
            "series": _build_empty_series(),
        }

    df = frame.copy()
    for column_name in (
        "quota",
        "nav",
        "total_assets",
        "inflow",
        "outflow",
        "shareholders",
    ):
        if column_name not in df.columns:
            df[column_name] = None

    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    df = df[df["date"].notna()]
    df["date_str"] = df["date"].dt.strftime("%Y-%m-%d")
    df = df[(df["date_str"] >= start_str) & (df["date_str"] <= end_str)].sort_values("date")

    if df["date_str"].duplicated().any():
        dups = sorted(df[df["date_str"].duplicated()]["date_str"].unique().tolist())
        raise ValueError(
            f"Observações com datas duplicadas encontradas no período solicitado: {dups}."
        )

    observations = len(df)
    expected_bdays = pd.bdate_range(start=start_str, end=end_str)
    observed_dates_set = set(df["date_str"].tolist())
    missing_weekdays = sum(
        1 for bday in expected_bdays if bday.strftime("%Y-%m-%d") not in observed_dates_set
    )

    if observations == 0:
        quality.append({
            "severity": "warning",
            "code": "NO_DATA",
            "message": f"Nenhuma observação encontrada para o intervalo solicitado ({start_str} a {end_str}).",
        })
        if missing_weekdays > 0:
            quality.append({
                "severity": "warning",
                "code": "MISSING_WEEKDAYS",
                "message": f"Estimativa de {missing_weekdays} dias úteis sem dados no período (estimativa não considera feriados nacionais).",
            })

        metrics = {
            "return_pct": None,
            "start_date": None,
            "end_date": None,
            "start_quota": None,
            "end_quota": None,
            "nav": None,
            "inflow": None,
            "outflow": None,
            "net_flow": None,
            "shareholders": None,
            "observations": 0,
            "missing_weekdays": missing_weekdays,
            "invalid_quotas": 0,
            "flow_missing_days": 0,
        }
        return {
            "metrics": metrics,
            "quality": quality,
            "series": _build_empty_series(),
        }

    df["quota_numeric"] = pd.to_numeric(df["quota"], errors="coerce")
    is_valid_quota = df["quota_numeric"].apply(
        lambda quota_value: pd.notna(quota_value)
        and quota_value > 0
        and math.isfinite(quota_value)
    )
    invalid_quotas = int((~is_valid_quota).sum())

    valid_quota_rows = df[is_valid_quota]
    valid_count = len(valid_quota_rows)

    start_date: str | None = None
    end_date: str | None = None
    start_quota: float | None = None
    end_quota: float | None = None
    return_pct: float | None = None

    if valid_count >= 1:
        first_row = valid_quota_rows.iloc[0]
        start_date = str(first_row["date_str"])
        start_quota = float(first_row["quota_numeric"])

        last_row = valid_quota_rows.iloc[-1]
        end_date = str(last_row["date_str"])
        end_quota = float(last_row["quota_numeric"])

        if valid_count >= 2:
            return_pct = ((end_quota / start_quota) - 1.0) * 100.0
        else:
            quality.append({
                "severity": "warning",
                "code": "INSUFFICIENT_DATA",
                "message": "Menos de duas cotas válidas encontradas no período; rentabilidade não pode ser calculada.",
            })
    else:
        quality.append({
            "severity": "warning",
            "code": "INSUFFICIENT_DATA",
            "message": "Nenhuma cota válida encontrada no período; rentabilidade não pode ser calculada.",
        })

    if start_date is not None and start_date > start_str:
        quality.append({
            "severity": "warning",
            "code": "CLIPPED_START",
            "message": f"Início do período ajustado: cota inicial disponível em {start_date}, posterior à data solicitada ({start_str}).",
        })
    if end_date is not None and end_date < end_str:
        quality.append({
            "severity": "warning",
            "code": "CLIPPED_END",
            "message": f"Fim do período ajustado: cota final disponível em {end_date}, anterior à data solicitada ({end_str}).",
        })

    if invalid_quotas > 0:
        quality.append({
            "severity": "warning",
            "code": "INVALID_QUOTAS",
            "message": f"Detectadas {invalid_quotas} cotas inválidas (nulas, não-positivas ou não-finitas) no período.",
        })

    if missing_weekdays > 0:
        quality.append({
            "severity": "warning",
            "code": "MISSING_WEEKDAYS",
            "message": f"Estimativa de {missing_weekdays} dias úteis sem dados no período (estimativa não considera feriados nacionais).",
        })

    last_obs_row = df.iloc[-1]
    nav_raw = last_obs_row.get("nav")
    nav = None
    if pd.notna(nav_raw):
        try:
            nav_float = float(nav_raw)
            if math.isfinite(nav_float):
                nav = nav_float
        except (ValueError, TypeError, OverflowError):
            nav = None

    sh_raw = last_obs_row.get("shareholders")
    shareholders = None
    if pd.notna(sh_raw):
        try:
            sh_float = float(sh_raw)
            if math.isfinite(sh_float) and sh_float >= 0 and sh_float.is_integer():
                shareholders = int(sh_float)
        except (ValueError, TypeError, OverflowError):
            shareholders = None

    if nav is None:
        quality.append({
            "severity": "warning",
            "code": "MISSING_FINAL_NAV",
            "message": "Patrimônio líquido não informado ou inválido na data final observada.",
        })

    if shareholders is None:
        quality.append({
            "severity": "warning",
            "code": "MISSING_FINAL_SHAREHOLDERS",
            "message": "Número de cotistas não informado ou inválido na data final observada.",
        })

    inflow_clean = df["inflow"].apply(_clean_flow_value)
    outflow_clean = df["outflow"].apply(_clean_flow_value)

    inflow_valid = inflow_clean.dropna()
    outflow_valid = outflow_clean.dropna()

    inflow = float(inflow_valid.sum()) if len(inflow_valid) > 0 else None
    outflow = float(outflow_valid.sum()) if len(outflow_valid) > 0 else None

    if inflow is None or outflow is None:
        net_flow = None
    else:
        net_flow = inflow - outflow

    flow_missing_mask = inflow_clean.isna() | outflow_clean.isna()
    flow_missing_days = int(flow_missing_mask.sum())

    if observations > 0 and inflow is None and outflow is None:
        quality.append({
            "severity": "warning",
            "code": "MISSING_FLOWS",
            "message": f"Dados de captação e resgate ausentes em todas as {observations} observações do período.",
        })
    elif flow_missing_days > 0 and (inflow is not None or outflow is not None):
        quality.append({
            "severity": "warning",
            "code": "PARTIAL_FLOWS",
            "message": f"Dados parciais de fluxo: {flow_missing_days} dias sem informação completa de captação ou resgate.",
        })
    elif missing_weekdays > 0 and (inflow is not None or outflow is not None):
        quality.append({
            "severity": "warning",
            "code": "PARTIAL_FLOWS",
            "message": f"Fluxos acumulados parciais: {missing_weekdays} dias úteis sem dados no período (estimativa de dias úteis não considera feriados nacionais).",
        })

    df["normalized"] = np.nan
    if start_quota is not None and start_quota > 0:
        df.loc[is_valid_quota, "normalized"] = (
            df.loc[is_valid_quota, "quota_numeric"] / start_quota
        ) * 100.0

    result_series = df[series_cols].copy()

    metrics = {
        "return_pct": return_pct,
        "start_date": start_date,
        "end_date": end_date,
        "start_quota": start_quota,
        "end_quota": end_quota,
        "nav": nav,
        "inflow": inflow,
        "outflow": outflow,
        "net_flow": net_flow,
        "shareholders": shareholders,
        "observations": observations,
        "missing_weekdays": missing_weekdays,
        "invalid_quotas": invalid_quotas,
        "flow_missing_days": flow_missing_days,
    }

    return {
        "metrics": metrics,
        "quality": quality,
        "series": result_series,
    }
