param([string]$Architecture = "x64")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $root "build/windows-$Architecture/publish"
$cmakeBuild = Join-Path $root "build/windows-$Architecture/cmake"
$env:ATIV_ENGINE_PATH = Join-Path $stage 'ativ-engine.exe'
$fixtures = Join-Path $root "build/native-fixtures"
python (Join-Path $root "script/create_smoke_media.py") $fixtures
if ($LASTEXITCODE -ne 0) { throw "Fixture creation failed" }

$env:ATIV_QT_TEST_ENGINE = $env:ATIV_ENGINE_PATH
$env:QT_QPA_PLATFORM = 'offscreen'
ctest --test-dir $cmakeBuild -C Release --output-on-failure
if ($LASTEXITCODE -ne 0) { throw 'Qt native tests failed' }

Remove-Item Env:ATIV_ENGINE_PATH
$env:ATIV_SMOKE_REPORT = Join-Path $env:RUNNER_TEMP 'ativ-native-smoke.json'
Remove-Item $env:ATIV_SMOKE_REPORT -ErrorAction SilentlyContinue
$app = Start-Process (Join-Path $stage 'ATIV.exe') -PassThru
try {
    for ($i=0; $i -lt 30 -and !(Test-Path $env:ATIV_SMOKE_REPORT); $i++) { Start-Sleep -Seconds 1 }
    if (!(Test-Path $env:ATIV_SMOKE_REPORT)) { throw 'Qt startup and engine preset smoke failed' }
} finally { if (!$app.HasExited) { Stop-Process -Id $app.Id } }

# Extract the actual portable ZIP and execute bundled discovery from that fresh payload.
$zip = Get-ChildItem (Join-Path $root 'packages') -Filter '*-windows-*.zip' | Select-Object -First 1
$installed = Join-Path $env:RUNNER_TEMP 'ATIV-portable-smoke'
Expand-Archive -LiteralPath $zip.FullName -DestinationPath $installed
$previousPath = $env:PATH
try {
    $env:PATH = ''
    & (Join-Path $installed 'ativ-engine.exe') check
    if ($LASTEXITCODE -ne 0) { throw 'Extracted portable runtime discovery failed' }
} finally { $env:PATH = $previousPath }
