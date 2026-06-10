# Build portable package for MSFS machines
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> Copy bundled SimConnect.dll"
& (Join-Path $PSScriptRoot "copy_simconnect_dll.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$BundledDll = Join-Path $Root "simconnect_native\lib\SimConnect.dll"
if (-not (Test-Path $BundledDll)) {
    Write-Error "Missing bundled DLL: $BundledDll"
}

Write-Host "==> Run tests"
py -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Build wheel"
py -m pip install --upgrade build pyinstaller -q
py -m build --wheel
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Wheel = Get-ChildItem dist\*.whl | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$Version = ($Wheel.BaseName -replace '^simconnect_h-','' -replace '-py3-none-any$','')

$Out = Join-Path $Root "dist\simconnect-H-portable-$Version"
if (Test-Path $Out) { Remove-Item $Out -Recurse -Force }
New-Item -ItemType Directory -Path $Out | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Out "examples") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Out "lib") | Out-Null

Copy-Item $Wheel.FullName $Out
Copy-Item $BundledDll (Join-Path $Out "SimConnect.dll")
Copy-Item $BundledDll (Join-Path $Out "lib\SimConnect.dll")
Copy-Item examples\diagnose_read.py (Join-Path $Out "examples\")
Copy-Item examples\install_and_test.bat (Join-Path $Out "examples\")

$ReadmePath = Join-Path $Out ([char]0x4F7F + [char]0x7528 + [char]0x8BF4 + [char]0x660E + ".txt")
$ReadmeLines = @(
    "simconnect-H $Version portable package",
    "========================",
    "",
    "Option A - with Python:",
    "  1. Extract anywhere",
    "  2. Start MSFS and enter a flight",
    "  3. Run examples\install_and_test.bat",
    "",
    "Option B - no Python (recommended on MSFS PC):",
    "  1. Extract anywhere",
    "  2. Start MSFS and enter a flight",
    "  3. Run SimConnect-Diagnose.exe",
    "",
    "Bundled SimConnect.dll is included (root and lib\).",
    "No SDK or Python required on the MSFS machine.",
    "",
    "Notes:",
    "  - Windows 64-bit only",
    "  - MSFS must be running in an active flight",
    "  - Do not replace bundled SimConnect.dll with old copies"
)
$ReadmeLines | Set-Content -Path $ReadmePath -Encoding UTF8

Write-Host "==> Build SimConnect-Diagnose.exe"
$AddData = "$BundledDll;simconnect_native/lib"
py -m PyInstaller `
    --noconfirm `
    --onefile `
    --name SimConnect-Diagnose `
    --distpath $Out `
    --workpath (Join-Path $Root "build\pyinstaller") `
    --specpath (Join-Path $Root "build\pyinstaller") `
    --paths $Root `
    --add-data $AddData `
    --hidden-import simconnect_native `
    examples\diagnose_read.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Zip = Join-Path $Root "dist\simconnect-H-portable-$Version.zip"
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path "$Out\*" -DestinationPath $Zip

Write-Host ""
Write-Host "Done:"
Write-Host ('  Out: ' + $Out)
Write-Host ('  Zip: ' + $Zip)
Write-Host ('  Whl: ' + $Wheel.FullName)
Write-Host ('  Dll: ' + $BundledDll)
