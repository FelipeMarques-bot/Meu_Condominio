$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Ambiente virtual não encontrado. Siga o README para criar o .venv."
}

Write-Host "Servidor em http://127.0.0.1:8000/ (Ctrl+C para parar)"
& ".\.venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000
