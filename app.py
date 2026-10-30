"""Cota Aberta - Terminal Editorial de Cotas e Integridade CVM.

Interface analítica desenvolvida em Streamlit e Plotly com foco em rigor estatístico,
auditoria de dados públicos da CVM e clareza metodológica.
"""

from __future__ import annotations

import datetime
import html
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from cota_aberta.storage import FundStore
    from cota_aberta.analytics import analyze_period
except ImportError:
    FundStore = None
    analyze_period = None

DATA_DIR = Path(os.environ.get("COTA_ABERTA_DATA_DIR", ROOT_DIR / "data"))
DEMO_DB_PATH = DATA_DIR / "demo.sqlite"
REAL_DB_PATH = DATA_DIR / "funds.sqlite"
DEMO_CSV_PATH = ROOT_DIR / "data" / "demo" / "inf_diario_demo.csv"
CSS_FILE_PATH = ROOT_DIR / "assets" / "style.css"

st.set_page_config(
    page_title="Cota Aberta — Terminal de Cotas CVM",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_custom_css() -> None:
    """Injeta o CSS editorial contido em assets/style.css."""
    if CSS_FILE_PATH.exists():
        try:
            with open(CSS_FILE_PATH, "r", encoding="utf-8") as file_handle:
                css_content = file_handle.read()
            st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
        except Exception:
            pass


def get_last_complete_month() -> str:
    """Retorna o último mês completo de referência no formato AAAA-MM."""
    today = datetime.date.today()
    first_of_month = today.replace(day=1)
    last_day_prev = first_of_month - datetime.timedelta(days=1)
    return last_day_prev.strftime("%Y-%m")


def format_cnpj(cnpj_raw: Any) -> str:
    """Formata CNPJ com máscara padrão caso contenha 14 dígitos numéricos."""
    if not cnpj_raw:
        return "N/D"
    formatted_text = re.sub(r"\D", "", str(cnpj_raw))
    if len(formatted_text) == 14:
        return f"{formatted_text[:2]}.{formatted_text[2:5]}.{formatted_text[5:8]}/{formatted_text[8:12]}-{formatted_text[12:]}"
    return str(cnpj_raw)


def format_currency_br(val: Optional[float]) -> str:
    """Formata valor numérico em moeda Real (R$) segundo convenção brasileira."""
    if val is None or pd.isna(val):
        return "N/D"
    try:
        formatted_text = f"{float(val):,.2f}"
        main_part, dec_part = formatted_text.split(".")
        main_part = main_part.replace(",", ".")
        return f"R$ {main_part},{dec_part}"
    except Exception:
        return str(val)


def format_number_br(val: Optional[float], decimals: int = 2) -> str:
    """Formata número com separadores brasileiros."""
    if val is None or pd.isna(val):
        return "N/D"
    try:
        fmt = f"{{:,.{decimals}f}}"
        formatted_text = fmt.format(float(val))
        main_part, separator, dec_part = formatted_text.partition(".")
        main_part = main_part.replace(",", ".")
        return f"{main_part},{dec_part}" if separator else main_part
    except Exception:
        return str(val)


def parse_date_safe(val: Any, default: datetime.date) -> datetime.date:
    """Converte valor para datetime.date com fallback seguro."""
    if val is None:
        return default
    if isinstance(val, (datetime.datetime, pd.Timestamp)):
        return val.date()
    if isinstance(val, datetime.date):
        return val
    try:
        formatted_text = str(val)[:10]
        return datetime.date.fromisoformat(formatted_text)
    except Exception:
        return default


def sanitize_label(text: Any) -> str:
    """Escapa texto para exibição segura sem injeção HTML."""
    if text is None:
        return ""
    return html.escape(str(text))


def get_fund_display_label(fund: Dict[str, Any]) -> str:
    """Constrói o rótulo descritivo do fundo para o seletor."""
    cnpj = format_cnpj(fund.get("cnpj"))
    name = fund.get("name")
    subclass = fund.get("subclass")
    obs = fund.get("observations")

    tokens: List[str] = []
    if name:
        tokens.append(f"{name} — CNPJ {cnpj}")
    else:
        tokens.append(f"CNPJ {cnpj}")

    if subclass:
        tokens.append(f"(Subclasse {subclass})")

    if obs is not None:
        tokens.append(f"[{obs} obs]")

    return " ".join(tokens)


def init_store_and_get_funds(mode: str) -> Tuple[Optional[Any], List[Dict[str, Any]], Optional[str]]:
    """Inicializa o FundStore correto conforme o modo e retorna a lista de fundos."""
    if FundStore is None:
        return None, [], "Módulo cota_aberta.storage não encontrado. Verifique a instalação do backend."

    error_msg: Optional[str] = None
    funds: List[Dict[str, Any]] = []

    if mode == "Demonstração":
        try:
            DEMO_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            store = FundStore(DEMO_DB_PATH)
            store.initialize()
            funds = store.list_funds()

            if not funds and DEMO_CSV_PATH.exists():
                try:
                    store.import_csv(str(DEMO_CSV_PATH), source_url="local-demo")
                    funds = store.list_funds()
                except Exception as imp_err:
                    error_msg = f"Aviso na importação demo inicial: {imp_err}"
            return store, funds, error_msg
        except Exception as error:
            return None, [], f"Erro ao inicializar banco de demonstração: {error}"

    elif mode == "Dados CVM":
        try:
            REAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            store = FundStore(REAL_DB_PATH)
            store.initialize()
            funds = store.list_funds()
            return store, funds, None
        except Exception as error:
            return None, [], f"Erro ao inicializar banco CVM oficial: {error}"

    return None, [], "Modo desconhecido selecionado."


def plot_frame_with_gaps(series_df: pd.DataFrame) -> pd.DataFrame:
    """Inclui lacunas gráficas sem inventar observações ou alterar os cálculos."""
    if series_df.empty or "date" not in series_df.columns:
        return series_df.copy()
    indexed = series_df.copy().set_index("date").sort_index()
    indexed.index = pd.to_datetime(indexed.index)
    weekdays = pd.bdate_range(indexed.index.min(), indexed.index.max())
    return indexed.reindex(indexed.index.union(weekdays)).rename_axis("date").reset_index()


def build_quota_chart(series_df: pd.DataFrame) -> go.Figure:
    """Gera gráfico da série de cota Base 100 com Plotly connectgaps=False."""
    series_df = plot_frame_with_gaps(series_df)
    fig = go.Figure()

    quota_col = (
        "base100"
        if "base100" in series_df.columns
        else ("normalized" if "normalized" in series_df.columns else None)
    )

    if not series_df.empty and "date" in series_df.columns and quota_col is not None:
        fig.add_trace(
            go.Scatter(
                x=series_df["date"],
                y=series_df[quota_col],
                mode="lines+markers",
                name="Cota Normalizada (Base 100)",
                connectgaps=False,
                line=dict(color="#C85A3F", width=2.2),
                marker=dict(size=4, color="#C85A3F"),
                hovertemplate="Data: %{x|%Y-%m-%d}<br>Cota Base 100: <b>%{y:.4f}</b><extra></extra>",
            )
        )

    fig.update_layout(
        title=dict(
            text="Evolução da Cota Normalizada (Início = 100) — Descontinuidades sem Interpolação",
            font=dict(family="Georgia, serif", size=15, color="#1E2022"),
        ),
        paper_bgcolor="#F9F8F6",
        plot_bgcolor="#FFFFFF",
        margin=dict(l=40, r=20, t=40, b=40),
        xaxis=dict(
            title="Data da Observação",
            gridcolor="#EBE8E1",
            linecolor="#D5D0C5",
            tickfont=dict(family="JetBrains Mono, monospace", size=10),
            title_font=dict(size=11, color="#5A6068"),
        ),
        yaxis=dict(
            title="Índice Base 100",
            gridcolor="#EBE8E1",
            linecolor="#D5D0C5",
            tickfont=dict(family="JetBrains Mono, monospace", size=10),
            title_font=dict(size=11, color="#5A6068"),
        ),
        hoverlabel=dict(
            bgcolor="#FFFFFF",
            font_size=12,
            font_family="JetBrains Mono, monospace",
        ),
        showlegend=False,
        height=360,
    )
    return fig


def build_nav_flows_chart(series_df: pd.DataFrame) -> go.Figure:
    """Gera gráfico duplo com Patrimônio Líquido e Fluxos (Captação / Resgate)."""
    series_df = plot_frame_with_gaps(series_df)
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        subplot_titles=("Patrimônio Líquido (R$)", "Movimentação Diária de Recursos (R$)"),
    )

    if not series_df.empty and "date" in series_df.columns:
        if "nav" in series_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=series_df["date"],
                    y=series_df["nav"],
                    mode="lines",
                    name="Patrimônio Líquido",
                    connectgaps=False,
                    line=dict(color="#2C4A5E", width=2),
                    hovertemplate="Data: %{x|%Y-%m-%d}<br>PL: R$ %{y:,.2f}<extra></extra>",
                ),
                row=1,
                col=1,
            )

        if "inflow" in series_df.columns:
            fig.add_trace(
                go.Bar(
                    x=series_df["date"],
                    y=series_df["inflow"],
                    name="Captação",
                    marker_color="#375F4B",
                    hovertemplate="Data: %{x|%Y-%m-%d}<br>Captação: R$ %{y:,.2f}<extra></extra>",
                ),
                row=2,
                col=1,
            )

        if "outflow" in series_df.columns:
            outflow_neg = -series_df["outflow"].abs()
            fig.add_trace(
                go.Bar(
                    x=series_df["date"],
                    y=outflow_neg,
                    name="Resgate (Saída)",
                    marker_color="#943D2C",
                    hovertemplate="Data: %{x|%Y-%m-%d}<br>Resgate: R$ %{y:,.2f}<extra></extra>",
                ),
                row=2,
                col=1,
            )

    fig.update_layout(
        paper_bgcolor="#F9F8F6",
        plot_bgcolor="#FFFFFF",
        margin=dict(l=40, r=20, t=40, b=40),
        height=420,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10, family="sans-serif"),
        ),
        barmode="relative",
    )
    fig.update_xaxes(gridcolor="#EBE8E1", linecolor="#D5D0C5", tickfont=dict(size=10))
    fig.update_yaxes(gridcolor="#EBE8E1", linecolor="#D5D0C5", tickfont=dict(size=10))
    return fig


def main() -> None:
    load_custom_css()

    st.sidebar.markdown("### Terminal Cota Aberta")
    mode = st.sidebar.radio(
        "Fonte de Dados",
        options=["Demonstração", "Dados CVM"],
        index=0,
        help="Demonstração: dados offline sintéticos pré-carregados. Dados CVM: dados oficiais baixados da autarquia.",
    )

    store, funds, init_error = init_store_and_get_funds(mode)

    if mode == "Demonstração":
        st.markdown(
            """
            <div class="synthetic-watermark">
                <span>⚠️</span>
                <div>
                    <strong>Modo Demonstração Ativo</strong> — Os dados exibidos são puramente sintéticos,
                    marcados educacionalmente para avaliação offline do terminal. Não refletem valores reais de
                    negociação nem constituem aconselhamento ou recomendação de investimentos.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.sidebar.info("Ambiente offline com dados sintéticos pré-carregados.")

    if mode == "Dados CVM" and store is not None:
        st.sidebar.markdown("---")
        st.sidebar.markdown("#### Obter dados da CVM")

        st.sidebar.warning(
            "Snapshot mensal: importar substitui os informes desse mês no banco. "
            "Envie o arquivo completo, não um recorte filtrado."
        )
        default_month = get_last_complete_month()
        with st.sidebar.form("form_download_cvm"):
            month_input = st.text_input(
                "Mês de referência (AAAA-MM)",
                value=default_month,
                help="Informe o mês no formato AAAA-MM (ex: 2026-09). Padrão é o último mês completo.",
            )
            refresh_cvm = st.checkbox("Baixar novamente, ignorando cache", value=False)
            submit_cvm = st.form_submit_button("Baixar informe CVM", width="stretch")

        if submit_cvm:
            month_clean = month_input.strip()
            if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", month_clean):
                st.sidebar.error("Mês inválido. Utilize o formato AAAA-MM (ex: 2026-09).")
            else:
                cmd = [
                    sys.executable,
                    "-m",
                    "cota_aberta.cli",
                    "import-cvm",
                    "--month",
                    month_clean,
                    "--db",
                    str(REAL_DB_PATH),
                ]
                if refresh_cvm:
                    cmd.append("--refresh")
                with st.spinner(f"Executando download do informe CVM {month_clean}..."):
                    try:
                        proc = subprocess.run(
                            cmd, capture_output=True, text=True, timeout=180, cwd=ROOT_DIR,
                            encoding="utf-8", errors="replace",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                        )
                        if proc.returncode == 0:
                            st.sidebar.success(f"Informe {month_clean} importado com sucesso!")
                            st.rerun()
                        else:
                            st.sidebar.error(
                                f"Erro no processo de importação CVM: {proc.stderr or proc.stdout}"
                            )
                    except subprocess.TimeoutExpired:
                        st.sidebar.error("Tempo limite excedido ao consultar servidor CVM (timeout de 180s).")
                    except Exception as ex:
                        st.sidebar.error(f"Falha na chamada do CLI da CVM: {ex}")

        st.sidebar.markdown("#### Importar arquivo CSV")
        uploaded_csv = st.sidebar.file_uploader(
            "Arquivo de informe (.csv)",
            type=["csv"],
            key="cvm_csv_uploader",
            help="Arquivo CSV de informe diário da CVM",
        )
        if uploaded_csv is not None:
            if st.sidebar.button("Ingerir CSV enviado", width="stretch", key="btn_ingest"):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
                    tmp_file.write(uploaded_csv.getbuffer())
                    tmp_path = tmp_file.name

                try:
                    with st.spinner("Importando arquivo CSV..."):
                        safe_name = re.sub(r"[^\w\-.]", "_", uploaded_csv.name)
                        res = store.import_csv(tmp_path, source_url=f"upload:{safe_name}")
                        rows_n = res.get("valid_rows", "N/D")
                        st.sidebar.success(f"Arquivo importado com sucesso: {rows_n} registros.")
                        st.rerun()
                except Exception as up_err:
                    st.sidebar.error(f"Falha ao importar CSV: {up_err}")
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass

    st.markdown(
        f"""
        <div class="masthead-container">
            <div>
                <h1 class="masthead-title">Cota Aberta</h1>
                <div class="masthead-subtitle">Fundos de investimento · dados públicos, cálculos explicados</div>
            </div>
            <div class="masthead-meta">
                Ambiente: <strong>{mode.upper()}</strong><br>
                Base: {REAL_DB_PATH.name if mode == "Dados CVM" else DEMO_DB_PATH.name}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if init_error:
        st.error(init_error)

    if not funds:
        if mode == "Dados CVM":
            st.info(
                "Nenhum informe de fundo encontrado no banco de dados oficial (`data/funds.sqlite`).\n\n"
                "Para iniciar a análise:\n"
                "1. Utilize o formulário no menu lateral para baixar um mês completo da CVM (ex: `2026-09`); ou\n"
                "2. Faça o envio de um arquivo CSV de informe diário pelo uploader na barra lateral.\n\n"
                "*O sistema permanece estritamente em modo de dados reais e não recorrerá silenciosamente à demonstração.*"
            )
        else:
            st.warning(
                "Nenhum dado sintético encontrado em `data/demo.sqlite` e o arquivo "
                "`data/demo/inf_diario_demo.csv` não estava presente para seed inicial."
            )
        return

    st.sidebar.markdown("---")
    st.sidebar.markdown("#### Selecionar Fundo")
    selected_fund = st.sidebar.selectbox(
        "Fundo por CNPJ / Subclasse",
        options=funds,
        format_func=get_fund_display_label,
        index=0,
    )

    f_first = selected_fund.get("first_date")
    f_last = selected_fund.get("last_date")

    today = datetime.date.today()
    min_date = parse_date_safe(f_first, today - datetime.timedelta(days=365))
    max_date = parse_date_safe(f_last, today)

    if min_date > max_date:
        min_date, max_date = max_date, min_date

    st.sidebar.markdown("#### Período de Análise")
    date_range = st.sidebar.date_input(
        "Intervalo temporal",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        help="Selecione a data inicial e final para o cálculo de retorno e fluxos.",
    )

    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_d, end_d = date_range[0], date_range[1]
    elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
        start_d = end_d = date_range[0]
    elif isinstance(date_range, datetime.date):
        start_d = end_d = date_range
    else:
        start_d, end_d = min_date, max_date

    start_str = start_d.strftime("%Y-%m-%d")
    end_str = end_d.strftime("%Y-%m-%d")

    fund_id = selected_fund["fund_id"]
    obs_df = store.read_observations(fund_id, start=start_str, end=end_str)

    if analyze_period is not None:
        analysis_result = analyze_period(obs_df, start=start_str, end=end_str)
    else:
        analysis_result = {"metrics": {}, "quality": [], "series": obs_df}

    metrics = analysis_result.get("metrics") or {}
    quality_list = analysis_result.get("quality") or []
    series_df = analysis_result.get("series")
    if series_df is None:
        series_df = pd.DataFrame()
    else:
        if "normalized" in series_df.columns and "base100" not in series_df.columns:
            series_df["base100"] = series_df["normalized"]
        elif "base100" in series_df.columns and "normalized" not in series_df.columns:
            series_df["normalized"] = series_df["base100"]

    return_pct = metrics.get("return_pct")
    start_date_eff = metrics.get("start_date")
    end_date_eff = metrics.get("end_date")
    start_quota = metrics.get("start_quota")
    end_quota = metrics.get("end_quota")
    nav_val = metrics.get("nav")
    shareholders_val = metrics.get("shareholders")
    inflow_val = metrics.get("inflow")
    outflow_val = metrics.get("outflow")
    net_flow_val = metrics.get("net_flow")
    obs_count = metrics.get("observations", len(obs_df))
    missing_weekdays = metrics.get("missing_weekdays", 0)
    invalid_quotas = metrics.get("invalid_quotas", 0)
    flow_missing_days = metrics.get("flow_missing_days", 0)

    fund_cnpj = format_cnpj(selected_fund.get("cnpj"))
    fund_name = selected_fund.get("name") or f"Fundo CNPJ {fund_cnpj}"
    fund_subclass = selected_fund.get("subclass")

    st.markdown(
        f"""
        <div style="margin-bottom: 16px;">
            <span style="font-family: Georgia, serif; font-size: 1.35rem; font-weight: 600; color: #1E2022;">
                {sanitize_label(fund_name)}
            </span>
            <span class="badge-info" style="margin-left: 8px;">CNPJ: {sanitize_label(fund_cnpj)}</span>
            {f'<span class="badge-info" style="margin-left: 4px;">Subclasse: {sanitize_label(fund_subclass)}</span>' if fund_subclass else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_overview, tab_quality, tab_methodology = st.tabs(
        ["Visão geral", "Qualidade dos dados", "Como calculamos"]
    )

    with tab_overview:
        ret_display = (
            f"{'+' if return_pct >= 0 else ''}{format_number_br(return_pct, 2)}%"
            if return_pct is not None and not pd.isna(return_pct) else "N/D"
        )
        cota_start_str = format_number_br(start_quota, 6)
        cota_end_str = format_number_br(end_quota, 6)

        date_start_label = str(start_date_eff)[:10] if start_date_eff else start_str
        date_end_label = str(end_date_eff)[:10] if end_date_eff else end_str
        last_observation_label = str(obs_df["date"].max())[:10] if not obs_df.empty else "N/D"

        flow_has_warning = (
            flow_missing_days > 0 or any("flow" in str(quality_item.get("code", "")).lower() for quality_item in quality_list)
        )
        flow_subtext = (
            f"⚠️ Parcial ({flow_missing_days} dias sem reporte)"
            if flow_has_warning
            else "Total no intervalo solicitado"
        )
        flow_components_text = (
            f"Cap: {format_currency_br(inflow_val)} · Resg: {format_currency_br(outflow_val)}"
            if inflow_val is not None and outflow_val is not None
            else ""
        )

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown(
                f"""
                <div class="metric-card accent">
                    <div class="metric-label">Retorno Acumulado</div>
                    <div class="metric-value" style="color: {'#375F4B' if (return_pct or 0) >= 0 else '#943D2C'};">
                        {ret_display}
                    </div>
                    <div class="metric-sub">
                        Cota: {cota_start_str} → {cota_end_str}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Patrimônio Líquido Final</div>
                    <div class="metric-value">{format_currency_br(nav_val)}</div>
                    <div class="metric-sub">Posição em {last_observation_label} (sem preenchimento)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col3:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Cotistas na Data Final</div>
                    <div class="metric-value">{format_number_br(shareholders_val, 0)}</div>
                    <div class="metric-sub">Posição em {last_observation_label}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col4:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Captação Líquida Período</div>
                    <div class="metric-value" style="color: {'#375F4B' if (net_flow_val or 0) >= 0 else '#943D2C'};">
                        {format_currency_br(net_flow_val)}
                    </div>
                    <div class="metric-sub" style="color: {'#A66E2E' if flow_has_warning else '#848B94'};">
                        {flow_subtext}
                        {f'<br><span style="font-size: 0.68rem; color: #5A6068;">{flow_components_text}</span>' if flow_components_text else ''}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            f"""
            <div style="font-size: 0.8rem; color: #5A6068; margin-top: 4px; margin-bottom: 14px; font-family: monospace;">
                Fórmula: R = [(Cota_{{{date_end_label}}} / Cota_{{{date_start_label}}}) - 1] × 100
                · Intervalo solicitado: [{start_str} a {end_str}]
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.caption(
            f"Captações reportadas: {format_currency_br(inflow_val)} · "
            f"Resgates reportados: {format_currency_br(outflow_val)} · "
            f"Fluxos de {start_str} a {end_str}, inclusive."
        )
        if quality_list:
            st.warning(
                f"{len(quality_list)} alertas neste recorte. "
                "Valores ausentes e somas parciais exigem atenção; veja Qualidade dos dados."
            )

        if not series_df.empty:
            quota_fig = build_quota_chart(series_df)
            st.plotly_chart(quota_fig, width="stretch")

            nav_flows_fig = build_nav_flows_chart(series_df)
            st.plotly_chart(nav_flows_fig, width="stretch")
        else:
            st.info("Não há observações suficientes no intervalo selecionado para compor os gráficos.")

        st.markdown('<div class="section-header"><h3 class="section-title">Observações do Período e Proveniência</h3></div>', unsafe_allow_html=True)
        if not obs_df.empty:
            display_cols = [
                col
                for col in [
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
                if col in obs_df.columns
            ]
            st.dataframe(obs_df[display_cols], width="stretch", height=240)

            csv_export = obs_df[display_cols].to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Exportar observações com proveniência (CSV)",
                data=csv_export,
                file_name=f"cota_aberta_{re.sub(r'[^0-9]', '', str(fund_cnpj))}_{start_str}_{end_str}.csv",
                mime="text/csv",
            )
        else:
            st.write("Nenhum registro para exibir na tabela.")

    with tab_quality:
        st.markdown(
            """
            <div style="background-color: #FCF8F2; border-left: 4px solid #A66E2E; padding: 12px 14px; margin-bottom: 20px; font-size: 0.86rem; color: #1E2022;">
                <strong>Critério de Auditoria Temporal:</strong> A verificação de descontinuidades na série
                considera estritamente <strong>dias de semana (segunda a sexta-feira)</strong> e
                <strong>não desconta feriados nacionais</strong> (B3 ou feriados bancários). Feriados nacionais
                sem pregão podem ser computados como dias úteis sem reporte de cota.
            </div>
            """,
            unsafe_allow_html=True,
        )

        qcol1, qcol2, qcol3, qcol4 = st.columns(4)
        with qcol1:
            st.metric("Total de Observações", obs_count)
        with qcol2:
            st.metric("Dias de semana sem informe", missing_weekdays)
        with qcol3:
            st.metric("Cotas Inválidas/Nulas", invalid_quotas)
        with qcol4:
            st.metric("Dias sem Reporte de Fluxo", flow_missing_days)

        st.markdown('<div class="section-header"><h3 class="section-title">Diagnóstico de Inconsistências e Alertas</h3></div>', unsafe_allow_html=True)
        if quality_list:
            q_table = []
            for item in quality_list:
                sev = item.get("severity", "INFO").upper()
                q_table.append(
                    {
                        "Severidade": sev,
                        "Código": item.get("code", "N/D"),
                        "Descrição": item.get("message", "Sem descrição"),
                    }
                )
            st.table(q_table)
        else:
            st.success("Nenhuma inconformidade de integridade detectada na série analisada.")

    with tab_methodology:
        st.markdown(
            """

            O retorno é calculado com base nas cotas líquidas registradas nos pontos de negociação efetiva inicial e final:
            """
        )
        st.latex(r"R = \left(\frac{C_{\text{fim}}}{C_{\text{início}}} - 1\right) \times 100")
        st.markdown(
            """
            - **$C_{\\text{início}}$**: Primeira cota válida encontrada no intervalo solicitado.
            - **$C_{\\text{fim}}$**: Última cota válida encontrada no intervalo solicitado.
            - Os limites temporais efetivos de cotação podem diferir dos dias de calendário solicitados se o início ou fim recaírem em finais de semana ou feriados.

            ---

            Para viabilizar a comparação padronizada da evolução patrimonial da cota:
            """
        )
        st.latex(r"\text{Cota}_{\text{base100}}(t) = \frac{C(t)}{C_{\text{início}}} \times 100")
        st.markdown(
            """
            - **Sem Interpolação Linear (`connectgaps=False`)**: O terminal **não preenche** descontinuidades
              na série temporal. Caso haja ausência de informe em determinado dia útil, a linha do gráfico é
              interrompida para refletir a lacuna verídica no histórico público.

            ---

            """
        )
        st.latex(r"\text{Captação Total} = \sum_{t=\text{início}}^{\text{fim}} \text{Captação}_t")
        st.latex(r"\text{Resgate Total} = \sum_{t=\text{início}}^{\text{fim}} \text{Resgate}_t")
        st.latex(r"\text{Fluxo Líquido} = \text{Captação Total} - \text{Resgate Total}")
        st.markdown(
            """
            - O somatório de captações e resgates é apurado de forma inclusiva em todo o intervalo solicitado $[start, end]$.
            - Quando houver dias com ausência de reporte no campo de movimentação, o total é explicitamente sinalizado como **parcial**.

            ---

            - Os indicadores de Patrimônio Líquido (PL) e Cotistas reportados na visão resumida refletem a posição
              **estrita do último informe diário disponível** no período selecionado.
            - **Política Anti-Stale-Fill**: O terminal não realiza propagação artificial (*forward-fill*) de valores de PL
              em dias não reportados pelo administrador do fundo.

            ---

            - A contagem de dias úteis baseia-se exclusivamente no calendário semanal (segunda a sexta-feira) e **não possui ciência de feriados municipais, estaduais ou nacionais**. Feriados oficiais da B3 podem gerar alertas de dias úteis sem cota.
            - **Sem Aconselhamento**: O *Cota Aberta* é uma aplicação de auditoria, transparência e análise quantitativa de dados públicos da CVM. Não constitui, em nenhuma hipótese, oferta, recomendação de investimento ou consultoria financeira.
            """
        )

    if store is not None:
        with st.expander("Auditoria de Ingestão e Histórico de Arquivos no Banco", expanded=False):
            try:
                hist = store.import_history()
                if hist:
                    st.dataframe(pd.DataFrame(hist), width="stretch")
                else:
                    st.write("Nenhum histórico de importação registrado até o momento.")
            except Exception as hist_err:
                st.write(f"Histórico indisponível: {hist_err}")

            st.caption(
                "A auditoria de ingestão registra os arquivos carregados localmente no banco SQLite. "
                "A presença de um lote não implica atualização em tempo real nem substitui as obrigações regulatórias dos administradores perante a CVM."
            )


if __name__ == "__main__":
    main()
