param(
    [ValidateSet("x64", "ARM64")][string]$Architecture = "x64"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$version = ((Select-String -Path (Join-Path $root "Cargo.toml") -Pattern '^version = "([^"]+)"').Matches[0].Groups[1].Value)
$version = if ($env:ATIV_VERSION) { $env:ATIV_VERSION } else { $version }
$numericVersion = $version -replace "-dev\.", "."
$label = $Architecture.ToLowerInvariant()
$rustTarget = if ($Architecture -eq "ARM64") { "aarch64-pc-windows-msvc" } else { "x86_64-pc-windows-msvc" }
$runtime = if ($Architecture -eq "ARM64") { "win-arm64" } else { "win-x64" }
$build = Join-Path $root "build/windows-$Architecture"
$publish = Join-Path $build "publish"
$packages = Join-Path $root "packages"
$ffmpegTarget = if ($Architecture -eq "ARM64") { "windows-arm64" } else { "windows-x86_64" }
$ffmpegRuntime = & python (Join-Path $root "script/ffmpeg_runtime.py") provision $ffmpegTarget
if ($LASTEXITCODE -ne 0) { throw "AVID ATIV FFmpeg runtime unavailable" }

rustup target add $rustTarget
cargo build --manifest-path (Join-Path $root "Cargo.toml") --release --locked --target $rustTarget -p ativ-engine -p ativ-update
if ($LASTEXITCODE -ne 0) { throw "Rust build failed" }
if (Test-Path $build) { Remove-Item -Recurse -Force $build }
New-Item -ItemType Directory -Force -Path $publish, $packages | Out-Null
dotnet publish (Join-Path $root "platform/windows/ATIV/ATIV.csproj") -c Release -r $runtime --self-contained true -p:Platform=$Architecture -p:Version=$version -p:AssemblyVersion=$numericVersion -p:FileVersion=$numericVersion -o $publish
if ($LASTEXITCODE -ne 0) { throw "Native build failed" }

Copy-Item (Join-Path $root "target/$rustTarget/release/ativ-engine.exe") $publish
Copy-Item (Join-Path $root "target/$rustTarget/release/ativ-update.exe") $publish
python (Join-Path $root "script/configure_distribution.py") $publish "windows-$label"
if ($LASTEXITCODE -ne 0) { throw "Distribution configuration failed" }
python (Join-Path $root "script/ffmpeg_runtime.py") stage $ffmpegTarget --runtime $ffmpegRuntime --binary $publish
if ($LASTEXITCODE -ne 0) { throw "ATIV FFmpeg runtime staging failed" }
Copy-Item (Join-Path $root "LICENSE") $publish
Copy-Item (Join-Path $root "THIRD_PARTY_NOTICES.md") $publish
python (Join-Path $root "script/collect_licenses.py") (Join-Path $publish "licenses") --target $rustTarget
if ($LASTEXITCODE -ne 0) { throw "License collection failed" }

if ($env:WINDOWS_CERTIFICATE_BASE64) {
    $certificate = Join-Path $build "signing.pfx"
    [IO.File]::WriteAllBytes($certificate, [Convert]::FromBase64String($env:WINDOWS_CERTIFICATE_BASE64))
    $kits = ${env:ProgramFiles(x86)}
    $signTool = Get-ChildItem "$kits/Windows Kits/10/bin/*/x64/signtool.exe" | Sort-Object FullName | Select-Object -Last 1
    if (!$signTool) { throw "signtool.exe was not found." }
    Get-ChildItem $publish -Filter *.exe | ForEach-Object {
        & $signTool.FullName sign /fd SHA256 /td SHA256 /tr http://timestamp.digicert.com /f $certificate /p $env:WINDOWS_CERTIFICATE_PASSWORD $_.FullName
        if ($LASTEXITCODE -ne 0) { throw "Code signing failed" }
    }
    # The installer is signed below using the same temporary certificate.
}

python (Join-Path $root "script/ffmpeg_runtime.py") finish $ffmpegTarget --binary $publish
if ($LASTEXITCODE -ne 0) { throw "Signed ATIV FFmpeg runtime recording failed" }
python (Join-Path $root "script/validate_package.py") $publish "windows-$label"
if ($LASTEXITCODE -ne 0) { throw "Packaged ATIV FFmpeg runtime validation failed" }

$zip = Join-Path $packages "ATIV-$version-windows-$label.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "$publish/*" -DestinationPath $zip -CompressionLevel Optimal
Write-Output $zip

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (!$iscc) {
    $candidate = "${env:ProgramFiles(x86)}/Inno Setup 6/ISCC.exe"
    if (!(Test-Path $candidate)) { throw "Install Inno Setup 6 to build the native installer" }
    $isccPath = $candidate
} else { $isccPath = $iscc.Source }
$appName = if ($env:ATIV_CHANNEL -eq "development") { "ATIV Development" } else { "ATIV" }
$channelSuffix = if ($env:ATIV_CHANNEL -eq "development") { ".development" } else { "" }
$allowed = if ($Architecture -eq "ARM64") { "arm64" } else { "x64os" }
& $isccPath "/DVersion=$version" "/DAppName=$appName" "/DChannelSuffix=$channelSuffix" "/DArchitecture=$allowed" "/DLabel=$label" "/DPublishDirectory=$publish" "/DOutputDirectory=$packages" (Join-Path $root "platform/windows/installer/ATIV.iss")
if ($LASTEXITCODE -ne 0) { throw "Installer compilation failed" }
$installer = Join-Path $packages "ATIV-$version-windows-$label-setup.exe"
if ($env:WINDOWS_CERTIFICATE_BASE64) {
    try {
        & $signTool.FullName sign /fd SHA256 /td SHA256 /tr http://timestamp.digicert.com /f $certificate /p $env:WINDOWS_CERTIFICATE_PASSWORD $installer
        if ($LASTEXITCODE -ne 0) { throw "Installer signing failed" }
        & $signTool.FullName verify /pa $installer
        if ($LASTEXITCODE -ne 0) { throw "Installer signature verification failed" }
    } finally { Remove-Item $certificate -ErrorAction SilentlyContinue }
}
python (Join-Path $root "script/validate_package.py") $publish "windows-$label"
if ($LASTEXITCODE -ne 0) { throw "Package validation failed" }
Write-Output $installer
