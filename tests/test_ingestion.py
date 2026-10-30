"""Testes unitários para o módulo de ingestão e normalização de dados da CVM."""

import io
import traceback
import pytest

from cota_aberta.ingestion import (
    parse_cnpj,
    parse_cvm_records,
    parse_date,
    parse_integer,
    parse_numeric,
    parse_subclass,
    rows_have_equal_values,
    sanitize_source_url,
)


def test_sanitize_source_url():
    """Valida a remoção de credenciais, queries e fragmentos de URLs de proveniência."""
    assert (
        sanitize_source_url("https://usuario:segredo123@dados.cvm.gov.br/arquivo.zip?token=xyz#topo")
        == "https://dados.cvm.gov.br/arquivo.zip"
    )
    assert (
        sanitize_source_url("https://dados.cvm.gov.br/arquivo.zip")
        == "https://dados.cvm.gov.br/arquivo.zip"
    )
    assert sanitize_source_url("local") == "local"
    assert sanitize_source_url(None) == "local"


def test_sanitize_source_url_fails_closed_on_invalid_port_and_malformed():
    """Garante que URLs com portas fora da faixa ou formatos inválidos falhem fechadas."""
    with pytest.raises(ValueError, match="Falha ao sanitizar URL"):
        sanitize_source_url("https://usuario:segredo@dados.cvm.gov.br:99999/arquivo.zip")

    with pytest.raises(ValueError, match="Falha ao sanitizar URL"):
        sanitize_source_url("https://usuario:segredo@dados.cvm.gov.br:invalid_port/arquivo.zip")

    with pytest.raises(ValueError, match="Falha ao sanitizar URL"):
        sanitize_source_url("http://usuario:segredo@[")


def test_cnpj_normalization():
    """Valida a normalização de dígitos de CNPJ para 14 caracteres e rejeição de letras."""
    assert parse_cnpj("01.234.567/0001-89") == "01234567000189"
    assert parse_cnpj("1234567000189") == "01234567000189"
    assert parse_cnpj("") is None
    assert parse_cnpj(None) is None
    assert parse_cnpj("123456789012345") is None
    assert parse_cnpj("abc123") is None
    assert parse_cnpj("01.234.567/0001-89A") is None


def test_subclass_preservation_and_null_not_zero():
    """Valida que subclasses nulas e subclasse '0' são diferenciadas (Null != zero)."""
    assert parse_subclass(None) == ""
    assert parse_subclass("") == ""
    assert parse_subclass("null") == ""
    assert parse_subclass("NULL") == ""
    assert parse_subclass("0") == "0"
    assert parse_subclass("CLASSE_A") == "CLASSE_A"


def test_parse_date():
    """Valida rejeição de datas inválidas e aceitação de formato ISO."""
    assert parse_date("2024-01-15") == "2024-01-15"
    assert parse_date("20240115") == "2024-01-15"
    assert parse_date("2024-02-31") is None
    assert parse_date("invalid_date") is None
    assert parse_date("") is None


def test_parse_numeric():
    """Valida suporte a ponto, vírgula, valores nulos e não-finitos."""
    val, is_bad = parse_numeric("123.45")
    assert val == 123.45 and not is_bad

    val, is_bad = parse_numeric("123,45")
    assert val == 123.45 and not is_bad

    val, is_bad = parse_numeric("0,0")
    assert val == 0.0 and not is_bad

    val, is_bad = parse_numeric("")
    assert val is None and not is_bad

    val, is_bad = parse_numeric("NULL")
    assert val is None and not is_bad

    val, is_bad = parse_numeric("inf")
    assert val is None and is_bad

    val, is_bad = parse_numeric("texto_invalido")
    assert val is None and is_bad


def test_parse_integer():
    """Valida que valores fracionários, negativos ou não finitos são rejeitados."""
    val, is_bad = parse_integer("15")
    assert val == 15 and not is_bad

    val, is_bad = parse_integer("0")
    assert val == 0 and not is_bad

    val, is_bad = parse_integer("1.4")
    assert val is None and is_bad

    val, is_bad = parse_integer("-5")
    assert val is None and is_bad

    val, is_bad = parse_integer("inf")
    assert val is None and is_bad

    val, is_bad = parse_integer(None)
    assert val is None and not is_bad


def test_rows_have_equal_values_exact_comparison():
    """Valida comparação estrita sem tolerância para cotas e patrimônio."""
    row_base = {
        "quota": 100.0,
        "nav": 1000.0,
        "total_assets": 1000.0,
        "inflow": 0.0,
        "outflow": 0.0,
        "shareholders": 10,
    }
    row_identical = dict(row_base)
    assert rows_have_equal_values(row_base, row_identical)

    row_micro_diff = dict(row_base, quota=100.000001)
    assert not rows_have_equal_values(row_base, row_micro_diff)

    row_nav_diff = dict(row_base, nav=1000.00001)
    assert not rows_have_equal_values(row_base, row_nav_diff)

    row_shareholders_diff = dict(row_base, shareholders=11)
    assert not rows_have_equal_values(row_base, row_shareholders_diff)


def test_cvm_csv_parsing_legacy_and_current_aliases():
    """Valida leitura de CSVs com formatos legado (CNPJ_FUNDO) e atual (CNPJ_FUNDO_CLASSE)."""
    legacy_csv = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "01.234.567/0001-89;2024-01-02;1000000;100.50;990000;5000;2000;15\n"
    )
    obs, funds, audit = parse_cvm_records(io.StringIO(legacy_csv))
    fund_id = "01234567000189:"
    assert (fund_id, "2024-01-02") in obs
    assert obs[(fund_id, "2024-01-02")]["quota"] == 100.50
    assert audit["valid_rows"] == 1
    assert audit["rejected_rows"] == 0

    current_csv = (
        "CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "01.234.567/0001-89;SUB_01;2024-01-02;1000000;100.50;990000;5000;2000;15\n"
    )
    obs, funds, audit = parse_cvm_records(io.StringIO(current_csv))
    fund_id_sub = "01234567000189:SUB_01"
    assert (fund_id_sub, "2024-01-02") in obs
    assert obs[(fund_id_sub, "2024-01-02")]["subclass"] == "SUB_01"


def test_utf8_bom_stripping():
    """Garante que cabeçalhos com UTF-8 BOM sejam processados com sucesso."""
    bom_csv = (
        "\ufeffCNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "01.234.567/0001-89;2024-01-02;1000000;100.50;990000;5000;2000;15\n"
    )
    obs, funds, audit = parse_cvm_records(io.StringIO(bom_csv))
    assert audit["valid_rows"] == 1
    assert audit["rejected_rows"] == 0


def test_leading_empty_lines_before_header():
    """Garante que linhas vazias antes do cabeçalho sejam ignoradas graciosamente."""
    csv_with_blanks = (
        "\n"
        "   \n"
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "01.234.567/0001-89;2024-01-02;1000000;100.50;990000;5000;2000;15\n"
    )
    obs, funds, audit = parse_cvm_records(io.StringIO(csv_with_blanks))
    assert audit["valid_rows"] == 1
    assert audit["rejected_rows"] == 0


def test_duplicate_header_rows_skipped_robustly():
    """Garante que linhas duplicadas de cabeçalho no fluxo sejam ignoradas sem rejeição."""
    csv_with_dup_header = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "01.234.567/0001-89;2024-01-02;1000000;100.50;990000;5000;2000;15\n"
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "01.234.567/0001-89;2024-01-03;1000000;101.00;990000;0;0;15\n"
    )
    obs, funds, audit = parse_cvm_records(io.StringIO(csv_with_dup_header))
    assert audit["valid_rows"] == 2
    assert audit["rejected_rows"] == 0


def test_duplicate_header_column_names_rejected():
    """Garante que cabeçalhos com colunas duplicadas sejam rejeitados com ValueError."""
    bad_header_csv = (
        "CNPJ_FUNDO;DT_COMPTC;VL_QUOTA;VL_QUOTA;VL_TOTAL;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "01.234.567/0001-89;2024-01-02;100.0;100.0;1000000;990000;0;0;10\n"
    )
    with pytest.raises(ValueError, match="colunas duplicadas"):
        parse_cvm_records(io.StringIO(bad_header_csv))


def test_malformed_truncated_and_extra_rows_counted_as_rejected():
    """Garante que linhas truncadas ou com colunas excedentes sejam contabilizadas em rejected_rows."""
    csv_malformed = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "01.234.567/0001-89;2024-01-02;1000000;100.50;990000;5000;2000;15\n"
        "01.234.567/0001-89;2024-01-03;1000000;100.50;990000\n"
        "01.234.567/0001-89;2024-01-04;1000000;100.50;990000;5000;2000;15;EXTRA;COLUMN\n"
    )
    obs, funds, audit = parse_cvm_records(io.StringIO(csv_malformed))
    assert audit["valid_rows"] == 1
    assert audit["rejected_rows"] == 2


def test_multi_month_rejection():
    """Garante que arquivos com mais de um mês sejam rejeitados."""
    multi_month_csv = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "01.234.567/0001-89;2024-01-02;1000000;100.50;990000;5000;2000;15\n"
        "01.234.567/0001-89;2024-02-01;1000000;101.00;990000;0;0;15\n"
    )
    with pytest.raises(ValueError, match="múltiplos meses"):
        parse_cvm_records(io.StringIO(multi_month_csv))


def test_conflicting_duplicate_keys_rejection():
    """Garante que linhas duplicadas para a mesma chave com valores divergentes rejeitem a importação inteira."""
    conflicting_csv = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "01.234.567/0001-89;2024-01-02;1000000;100.00;990000;0;0;10\n"
        "01.234.567/0001-89;2024-01-02;1000000;105.00;990000;0;0;10\n"
    )
    with pytest.raises(ValueError, match="Conflito de dados para a chave"):
        parse_cvm_records(io.StringIO(conflicting_csv))


def test_identical_duplicate_keys_counted():
    """Linhas idênticas para a mesma chave são desduplicadas e contabilizadas no sumário de auditoria."""
    identical_csv = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "01.234.567/0001-89;2024-01-02;1000000;100.00;990000;0;0;10\n"
        "01.234.567/0001-89;2024-01-02;1000000;100.00;990000;0;0;10\n"
    )
    obs, funds, audit = parse_cvm_records(io.StringIO(identical_csv))
    assert audit["valid_rows"] == 1
    assert audit["duplicate_rows"] == 1
    assert audit["total_rows"] == 2


def test_sanitization_error_traceback_hides_untrusted_port():
    sensitive_marker = "private_port_marker"
    sensitive_password = "private_password_marker"
    source_url = f"https://usuario:{sensitive_password}@dados.cvm.gov.br:{sensitive_marker}/"
    with pytest.raises(ValueError) as captured:
        sanitize_source_url(source_url)
    formatted_error = "".join(traceback.format_exception(captured.value))
    assert sensitive_marker not in formatted_error
    assert sensitive_password not in formatted_error
