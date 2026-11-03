# Đóng gói giao diện thành exe (thư mục dist\EduXploreAdHelper, kèm adb + zip để gửi máy khác).
# Dùng venv sạch để exe không kéo theo thư viện thừa. Chạy:  powershell -File build_exe.ps1
param(
    [string]$Venv = "$env:TEMP\eduxplore_adhelper_venv",
    [string]$PlatformTools = "C:\platform-tools-latest-windows\platform-tools"   # nơi có adb.exe + 2 DLL
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path "$Venv\Scripts\python.exe")) {
    python -m venv $Venv
}
& "$Venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& "$Venv\Scripts\python.exe" -m pip install --quiet opencv-python-headless numpy websockets pyinstaller

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& "$Venv\Scripts\python.exe" -m PyInstaller --noconfirm --windowed --name EduXploreAdHelper `
    --add-data "templates;templates" --collect-submodules websockets gui_app.py

$out = "dist\EduXploreAdHelper"
New-Item -ItemType Directory -Force "$out\adb" | Out-Null
foreach ($f in "adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll") {
    Copy-Item "$PlatformTools\$f" "$out\adb\" -Force
}
Copy-Item "HUONG_DAN.txt" $out -Force
Compress-Archive -Path $out -DestinationPath "dist\EduXploreAdHelper.zip" -Force
Write-Host "Xong: $out  và  dist\EduXploreAdHelper.zip"
