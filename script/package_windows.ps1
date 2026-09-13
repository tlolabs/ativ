param(
    [ValidateSet("x64", "ARM64")][string]$Architecture = "x64",
    [Parameter(Mandatory = $true)][string]$FfmpegDirectory
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$version = ((Select-String -Path (Join-Path $root "Cargo.toml") -Pattern '^version = "([^"]+)"').Matches[0].Groups[1].Value)
$rustTarget = if ($Architecture -eq "ARM64") { "aarch64-pc-windows-msvc" } else { "x86_64-pc-windows-msvc" }
$runtime = if ($Architecture -eq "ARM64") { "win-arm64" } else { "win-x64" }
$build = Join-Path $root "build/windows-$Architecture"
$publish = Join-Path $build "publish"
$packages = Join-Path $root "packages"
$ffmpeg = Join-Path $FfmpegDirectory "ffmpeg.exe"
$ffprobe = Join-Path $FfmpegDirectory "ffprobe.exe"

if (!(Test-Path $ffmpeg) -or !(Test-Path $ffprobe)) { throw "Verified FFmpeg and ffprobe binaries are required." }
$ffmpegVersion = & $ffmpeg -version | Select-Object -First 1
if ($ffmpegVersion -notmatch 'ffmpeg version n9\.0\.1') { throw "Expected the pinned FFmpeg 9.0.1 build, got: $ffmpegVersion" }

rustup target add $rustTarget
cargo build --manifest-path (Join-Path $root "Cargo.toml") --release --locked --target $rustTarget -p avid-engine
if (Test-Path $build) { Remove-Item -Recurse -Force $build }
New-Item -ItemType Directory -Force -Path $publish, $packages | Out-Null
dotnet publish (Join-Path $root "platform/windows/AVID/AVID.csproj") -c Release -r $runtime --self-contained true -p:Platform=$Architecture -o $publish

Copy-Item (Join-Path $root "target/$rustTarget/release/avid-engine.exe") $publish
Copy-Item $ffmpeg $publish
Copy-Item $ffprobe $publish
Copy-Item (Join-Path $root "LICENSE") $publish
Copy-Item (Join-Path $root "THIRD_PARTY_NOTICES.md") $publish
if (Test-Path (Join-Path $FfmpegDirectory "FFMPEG_LICENSE.txt")) { Copy-Item (Join-Path $FfmpegDirectory "FFMPEG_LICENSE.txt") $publish }
(& $ffmpeg -buildconf 2>&1) | Set-Content (Join-Path $publish "FFMPEG_BUILD_CONFIGURATION.txt")

if ($env:WINDOWS_CERTIFICATE_BASE64) {
    $certificate = Join-Path $build "signing.pfx"
    [IO.File]::WriteAllBytes($certificate, [Convert]::FromBase64String($env:WINDOWS_CERTIFICATE_BASE64))
    $kits = ${env:ProgramFiles(x86)}
    $signTool = Get-ChildItem "$kits/Windows Kits/10/bin/*/x64/signtool.exe" | Sort-Object FullName | Select-Object -Last 1
    if (!$signTool) { throw "signtool.exe was not found." }
    Get-ChildItem $publish -Filter *.exe | ForEach-Object {
        & $signTool.FullName sign /fd SHA256 /td SHA256 /tr http://timestamp.digicert.com /f $certificate /p $env:WINDOWS_CERTIFICATE_PASSWORD $_.FullName
    }
    Remove-Item $certificate
}

$zip = Join-Path $packages "AVID-$version-windows-$Architecture.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "$publish/*" -DestinationPath $zip -CompressionLevel Optimal
Write-Output $zip
