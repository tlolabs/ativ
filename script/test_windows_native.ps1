param([string]$Architecture = "x64")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $root "build/windows-$Architecture/publish"
$env:ATIV_ENGINE_PATH = Join-Path $stage 'ativ-engine.exe'
dotnet run --project (Join-Path $root 'platform/windows/Tests/NativeIntegration.csproj')
if ($LASTEXITCODE -ne 0) { throw 'C# native engine integration failed' }
Remove-Item Env:ATIV_ENGINE_PATH
$env:ATIV_SMOKE_REPORT = Join-Path $env:RUNNER_TEMP 'ativ-native-smoke.json'
Remove-Item $env:ATIV_SMOKE_REPORT -ErrorAction SilentlyContinue
$app = Start-Process (Join-Path $stage 'ATIV.exe') -PassThru
try {
    for ($i=0; $i -lt 30 -and !(Test-Path $env:ATIV_SMOKE_REPORT); $i++) { Start-Sleep -Seconds 1 }
    if (!(Test-Path $env:ATIV_SMOKE_REPORT)) { throw 'WinUI startup and engine preset smoke failed' }
} finally { if (!$app.HasExited) { Stop-Process -Id $app.Id } }
$installer = Get-ChildItem (Join-Path $root 'packages') -Filter '*-setup.exe' | Select-Object -First 1
$installDir = Join-Path $env:RUNNER_TEMP 'ATIV-installed-smoke'
$setup = Start-Process $installer.FullName -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/DIR=`"$installDir`"") -Wait -PassThru
if ($setup.ExitCode -ne 0 -or !(Test-Path "$installDir/ATIV.exe")) { throw 'Installer smoke failed' }
# Exercise an upgrade over an existing installation.
$upgrade = Start-Process $installer.FullName -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/DIR=`"$installDir`"") -Wait -PassThru
if ($upgrade.ExitCode -ne 0) { throw 'Installer upgrade failed' }
$uninstall = Start-Process "$installDir/unins000.exe" -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -Wait -PassThru
if ($uninstall.ExitCode -ne 0 -or (Test-Path "$installDir/ATIV.exe")) { throw 'Uninstall smoke failed' }
