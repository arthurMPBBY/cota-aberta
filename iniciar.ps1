$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Ambiente .venv não encontrado. Siga a instalação no README.md antes de iniciar.'
}
Push-Location -LiteralPath $PSScriptRoot
try {
    & $pythonPath -m streamlit run app.py --server.address=127.0.0.1
}
finally {
    Pop-Location
}
