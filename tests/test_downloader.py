"""Testes unitários offline para o módulo de download de informes diários da CVM."""

import io
import zipfile
from pathlib import Path
import pytest

from cota_aberta.downloader import download_cvm_month, validate_month_format


def _create_sample_zip_bytes() -> bytes:
    """Cria o conteúdo em bytes de um arquivo ZIP válido contendo um CSV simples."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as sample_archive:
        sample_archive.writestr("test.csv", "CNPJ_FUNDO;DT_COMPTC\n12.345.678/0001-95;2024-01-02\n")
    return buf.getvalue()


class MockResponse:
    """Objeto mock para simular respostas da biblioteca requests."""

    def __init__(
        self,
        status_code: int = 200,
        content_chunks: list[bytes] | None = None,
    ) -> None:
        self.status_code = status_code
        self.chunks = content_chunks or []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def iter_content(self, chunk_size: int = 65536):
        yield from self.chunks


def test_month_format_validation():
    """Valida a validação de strings de competência mensal no formato YYYY-MM."""
    assert validate_month_format("2024-01") == "202401"
    assert validate_month_format("2026-12") == "202612"

    with pytest.raises(ValueError, match="Formato de mês inválido"):
        validate_month_format("202401")

    with pytest.raises(ValueError, match="Formato de mês inválido"):
        validate_month_format("2024-13")

    with pytest.raises(ValueError, match="Ano fora da faixa"):
        validate_month_format("1999-01")


def test_download_success(tmp_path, monkeypatch):
    """Valida o download com sucesso e geração do arquivo ZIP no diretório de destino."""
    zip_bytes = _create_sample_zip_bytes()

    def mock_get(url, stream=True, timeout=60):
        return MockResponse(200, [zip_bytes])

    monkeypatch.setattr("requests.get", mock_get)

    path, url = download_cvm_month("2024-01", output_dir=tmp_path)
    assert path.exists()
    assert zipfile.is_zipfile(path)
    assert "202401" in path.name
    assert url.endswith("inf_diario_fi_202401.zip")


def test_download_cache_hit(tmp_path, monkeypatch):
    """Garante que se o arquivo ZIP já existir e for válido, nenhuma requisição HTTP seja disparada."""
    existing_zip = tmp_path / "inf_diario_fi_202401.zip"
    existing_zip.write_bytes(_create_sample_zip_bytes())

    called = False

    def mock_get(url, stream=True, timeout=60):
        nonlocal called
        called = True
        return MockResponse(200, [])

    monkeypatch.setattr("requests.get", mock_get)

    path, source_url = download_cvm_month("2024-01", output_dir=tmp_path, refresh=False)
    assert path == existing_zip
    assert not called
    assert source_url.endswith("inf_diario_fi_202401.zip")


def test_download_corrupt_cache_invalidated_and_redownloaded(tmp_path, monkeypatch):
    """Garante que arquivo em cache corrompido seja descartado e baixado novamente."""
    existing_zip = tmp_path / "inf_diario_fi_202401.zip"
    corrupt_zip_bytes = bytearray(_create_sample_zip_bytes())
    corrupt_zip_bytes[20:30] = b"\x00" * 10
    existing_zip.write_bytes(bytes(corrupt_zip_bytes))

    fresh_bytes = _create_sample_zip_bytes()
    download_occurred = False

    def mock_get(url, stream=True, timeout=60):
        nonlocal download_occurred
        download_occurred = True
        return MockResponse(200, [fresh_bytes])

    monkeypatch.setattr("requests.get", mock_get)

    path, source_url = download_cvm_month("2024-01", output_dir=tmp_path, refresh=False)
    assert download_occurred
    assert path == existing_zip
    assert zipfile.is_zipfile(path)


def test_download_http_404(tmp_path, monkeypatch):
    """Valida que status HTTP 404 levante FileNotFoundError informando a ausência do arquivo."""

    def mock_get(url, stream=True, timeout=60):
        return MockResponse(404, [])

    monkeypatch.setattr("requests.get", mock_get)

    with pytest.raises(FileNotFoundError, match="HTTP 404"):
        download_cvm_month("2024-01", output_dir=tmp_path)


def test_download_corrupt_zip(tmp_path, monkeypatch):
    """Valida que um arquivo com bytes corrompidos seja rejeitado e o arquivo temporário limpo."""

    def mock_get(url, stream=True, timeout=60):
        return MockResponse(200, [b"Not a valid zip content"])

    monkeypatch.setattr("requests.get", mock_get)

    with pytest.raises(ValueError, match="não é um arquivo ZIP válido"):
        download_cvm_month("2024-01", output_dir=tmp_path)

    temp_files = list(Path(tmp_path).glob("*.tmp"))
    assert len(temp_files) == 0


def test_download_size_overflow(tmp_path, monkeypatch):
    """Garante que ultrapassar o teto máximo interrompa o download e limpe o arquivo no Windows."""
    oversized_chunk = b"A" * 1024

    def mock_get(url, stream=True, timeout=60):
        return MockResponse(200, [oversized_chunk, oversized_chunk])

    monkeypatch.setattr("requests.get", mock_get)

    with pytest.raises(ValueError, match="excedeu o limite máximo"):
        download_cvm_month("2024-01", output_dir=tmp_path, max_size_bytes=512)

    temp_files = list(Path(tmp_path).glob("*.tmp"))
    assert len(temp_files) == 0


def test_refresh_preserves_old_zip_on_download_failure(tmp_path, monkeypatch):
    """Garante que falhas durante o refresh preservem o arquivo ZIP antigo intacto."""
    old_zip_path = tmp_path / "inf_diario_fi_202401.zip"
    initial_bytes = _create_sample_zip_bytes()
    old_zip_path.write_bytes(initial_bytes)

    def mock_get_fail(url, stream=True, timeout=60):
        return MockResponse(500, [])

    monkeypatch.setattr("requests.get", mock_get_fail)

    with pytest.raises(RuntimeError, match="HTTP 500"):
        download_cvm_month("2024-01", output_dir=tmp_path, refresh=True)

    assert old_zip_path.exists()
    assert old_zip_path.read_bytes() == initial_bytes


def test_oversized_cache_rejected_before_decompression(tmp_path, monkeypatch):
    cached_path = tmp_path / "inf_diario_fi_202401.zip"
    cached_path.write_bytes(_create_sample_zip_bytes())
    decompression_calls = []

    def record_decompression(archive):
        decompression_calls.append(archive.filename)
        return None

    def mock_get(url, stream=True, timeout=60):
        return MockResponse(404, [])

    monkeypatch.setattr("cota_aberta.downloader.MAX_UNCOMPRESSED_SIZE_BYTES", 1)
    monkeypatch.setattr(zipfile.ZipFile, "testzip", record_decompression)
    monkeypatch.setattr("requests.get", mock_get)

    with pytest.raises(FileNotFoundError, match="HTTP 404"):
        download_cvm_month("2024-01", output_dir=tmp_path)

    assert decompression_calls == []
    assert not cached_path.exists()
