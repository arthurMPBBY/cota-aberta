"""Testes automatizados da interface Streamlit do Cota Aberta utilizando AppTest."""

import datetime
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("COTA_ABERTA_DATA_DIR", str(tmp_path))


def test_app_smoke_demo() -> None:
    """Testa a inicialização padrão da aplicação no modo Demonstração."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    assert not at.exception, f"Exceções encontradas: {[exception.value for exception in at.exception]}"

    assert len(at.radio) >= 1
    assert at.radio[0].value == "Demonstração"

    all_markdown_text = " ".join([markdown_item.value for markdown_item in at.markdown])
    assert "Modo Demonstração" in all_markdown_text or "sintético" in all_markdown_text.lower(), (
        "O aviso explícito de dados sintéticos (marca d'água) deve estar presente no modo Demonstração."
    )

    assert "Cota Aberta" in all_markdown_text

    assert len(at.tabs) >= 3
    tab_labels = [tab.label for tab in at.tabs]
    assert "Visão geral" in tab_labels
    assert "Qualidade dos dados" in tab_labels
    assert "Como calculamos" in tab_labels

    assert "Retorno Acumulado" in all_markdown_text
    assert "Patrimônio Líquido Final" in all_markdown_text
    assert "Cotistas na Data Final" in all_markdown_text
    assert "Captação Líquida Período" in all_markdown_text

    plotly_elements = at.get("plotly_chart")
    assert len(plotly_elements) >= 2


def test_app_mode_switch_no_data() -> None:
    """Testa a transição para 'Dados CVM' e o estado explícito de ausência de dados."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    at.radio[0].set_value("Dados CVM").run()

    assert not at.exception, f"Exceções encontradas na transição: {[exception.value for exception in at.exception]}"
    assert at.radio[0].value == "Dados CVM"

    all_markdown_text = " ".join([markdown_item.value for markdown_item in at.markdown])

    assert "Modo Demonstração Ativo" not in all_markdown_text

    assert len(at.info) > 0
    info_text = " ".join([info_item.value for info_item in at.info])
    assert "funds.sqlite" in info_text
    assert len(at.selectbox) == 0


def test_app_methodology_content() -> None:
    """Valida que as convenções metodológicas, fórmulas e avisos legais constam na aplicação."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    all_markdown_text = " ".join([markdown_item.value for markdown_item in at.markdown])

    assert "recomendação" in all_markdown_text.lower()
    assert "feriados" in all_markdown_text.lower()
    assert "stale" in all_markdown_text.lower() or "preenchimento" in all_markdown_text.lower()


def test_app_date_filtering() -> None:
    """Testa a alteração de datas no período de análise."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    assert len(at.date_input) >= 1
    at.date_input[0].set_value((datetime.date(2025, 6, 2), datetime.date(2025, 6, 20))).run()
    assert not at.exception
