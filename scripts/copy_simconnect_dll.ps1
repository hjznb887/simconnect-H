# Copy SimConnect.dll from MSFS SDK into simconnect_native/lib/
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$DestDir = Join-Path $Root "simconnect_native\lib"
$Dest = Join-Path $DestDir "SimConnect.dll"

New-Item -ItemType Directory -Force -Path $DestDir | Out-Null

$candidates = @()

function Test-PathSafe([string]$Path) {
    if (-not $Path) { return $false }
    try {
        return Test-Path -LiteralPath $Path -ErrorAction Stop
    } catch {
        return $false
    }
}

function Add-FirstExistingPath([string[]]$Paths) {
    foreach ($p in $Paths) {
        if (Test-PathSafe $p) {
            $script:candidates += $p
            return $true
        }
    }
    return $false
}

if ($env:SIMCONNECT_DLL -and (Test-PathSafe $env:SIMCONNECT_DLL)) {
    Copy-Item -Force $env:SIMCONNECT_DLL $Dest
    Write-Host "Copied from SIMCONNECT_DLL -> $Dest"
    exit 0
}

$customSdk = @(
    "D:\MSFS SDK\SimConnect SDK\lib\SimConnect.dll"
)
if ($env:MSFS_SDK_ROOT) {
    $customSdk += (Join-Path $env:MSFS_SDK_ROOT "SimConnect SDK\lib\SimConnect.dll")
}
if ($env:MSFS_SDK) {
    $customSdk += (Join-Path $env:MSFS_SDK "SimConnect SDK\lib\SimConnect.dll")
}
if (Add-FirstExistingPath $customSdk) {
    # SDK copy wins when present
} else {
    $msfsInstallDirs = @(
        $env:MSFS_INSTALL_DIR,
        $env:MSFS_SIMULATOR_DIR,
        $env:STEAM_MSFS_DIR,
        "D:\SteamLibrary\steamapps\common\MicrosoftFlightSimulator",
        "C:\Program Files (x86)\Steam\steamapps\common\MicrosoftFlightSimulator",
        "E:\SteamLibrary\steamapps\common\MicrosoftFlightSimulator",
        "D:\SteamLibrary\steamapps\common\Microsoft Flight Simulator"
    )
    foreach ($dir in $msfsInstallDirs) {
        if (-not $dir) { continue }
        try {
            $dllPath = Join-Path $dir "SimConnect.dll"
        } catch {
            continue
        }
        if (Add-FirstExistingPath @($dllPath)) { break }
    }
}

$pf86 = ${env:ProgramFiles(x86)}
if (-not $pf86) { $pf86 = "C:\Program Files (x86)" }

$sdkRoot = Join-Path $pf86 "Microsoft SDKs\FlightSimulator"
if (Test-Path $sdkRoot) {
    Get-ChildItem -Path $sdkRoot -Recurse -Filter "SimConnect.dll" -ErrorAction SilentlyContinue |
        ForEach-Object { $candidates += $_.FullName }
}

$extra = @(
    (Join-Path $pf86 "Microsoft Flight Simulator SDK\SimConnect SDK\lib\SimConnect.dll")
)
if ($env:ProgramFiles) {
    $extra += (Join-Path $env:ProgramFiles "Microsoft Flight Simulator SDK\SimConnect SDK\lib\SimConnect.dll")
}
foreach ($p in $extra) {
    if (Test-PathSafe $p) { $candidates += $p }
}

$arlDll = Join-Path (Split-Path -Parent $Root) "ARL\SimConnect.dll"
if (Test-PathSafe $arlDll) {
    $candidates += $arlDll
}

try {
    $siteLines = & py -c "import site; print('\n'.join(site.getsitepackages()))" 2>$null
    if ($siteLines) {
        foreach ($site in $siteLines) {
            $site = $site.Trim()
            if (-not $site) { continue }
            $p = Join-Path $site "SimConnect\SimConnect.dll"
            if (Test-PathSafe $p) { $candidates += $p }
        }
    }
} catch {}

$src = $candidates | Select-Object -First 1
if (-not $src) {
    Write-Error "SimConnect.dll not found. Install MSFS SDK redistributable or set SIMCONNECT_DLL."
}

Copy-Item -Force $src $Dest
Write-Host "Copied: $src"
Write-Host "Target: $Dest"
