# Chạy server cục bộ để thử. Đặt EDUXPLORE_ADMIN_PASSWORD / EDUXPLORE_SECRET_KEY trước khi chạy khi triển khai thật.
param([string]$Venv = "$env:TEMP\eduxplore_server_venv", [int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path "$Venv\Scripts\python.exe")) { python -m venv $Venv }
& "$Venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if (-not $env:EDUXPLORE_ADMIN_PASSWORD) { $env:EDUXPLORE_ADMIN_PASSWORD = "admin123" }
Write-Host "Admin UI: http://127.0.0.1:$Port/admin/login  (mat khau: $env:EDUXPLORE_ADMIN_PASSWORD)"
Write-Host "API docs: http://127.0.0.1:$Port/docs"
& "$Venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port $Port
