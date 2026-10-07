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
$build = Join-Path $root "build/windows-$Architecture"
$publish = Join-Path $build "publish"
$packages = Join-Path $root "packages"
$ffmpegTarget = if ($Architecture -eq "ARM64") { "windows-arm64" } else { "windows-x86_64" }
$ffmpegRuntime = & python (Join-Path $root "script/ffmpeg_runtime.py") provision $ffmpegTarget
if ($LASTEXITCODE -ne 0) { throw "ATIV FFmpeg runtime unavailable" }

rustup target add $rustTarget
cargo build --manifest-path (Join-Path $root "Cargo.toml") --release --locked --target $rustTarget -p ativ-engine -p ativ-update
if ($LASTEXITCODE -ne 0) { throw "Rust build failed" }
if (Test-Path $build) { Remove-Item -Recurse -Force $build }
New-Item -ItemType Directory -Force -Path $publish, $packages | Out-Null

$cmakeBuild = Join-Path $build "cmake"
cmake -S (Join-Path $root "platform/qt") -B $cmakeBuild -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { throw "CMake configuration failed" }
cmake --build $cmakeBuild --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw "Qt build failed" }

$exeDir = if (Test-Path (Join-Path $cmakeBuild "Release/ATIV.exe")) { Join-Path $cmakeBuild "Release" } else { $cmakeBuild }
Copy-Item (Join-Path $exeDir "ATIV.exe") $publish
Copy-Item (Join-Path $exeDir "ativ-portable-update.exe") $publish

$assetsDir = Join-Path $publish "Assets"
New-Item -ItemType Directory -Force -Path $assetsDir | Out-Null
Copy-Item (Join-Path $root "platform/windows/Assets/ATIV.ico") (Join-Path $assetsDir "ATIV.ico")

$windeployqt = if ($env:QT_DIR) { Join-Path $env:QT_DIR "bin/windeployqt.exe" } else { "windeployqt" }
& $windeployqt --release --no-translations --no-opengl-sw (Join-Path $publish "ATIV.exe")
if ($LASTEXITCODE -ne 0) { throw "windeployqt failed" }

Copy-Item (Join-Path $root "target/$rustTarget/release/ativ-engine.exe") $publish
Copy-Item (Join-Path $root "target/$rustTarget/release/ativ-update.exe") $publish
python (Join-Path $root "script/configure_distribution.py") $publish "windows-$label"
if ($LASTEXITCODE -ne 0) { throw "Distribution configuration failed" }
python (Join-Path $root "script/ffmpeg_runtime.py") stage $ffmpegTarget --runtime $ffmpegRuntime --binary $publish
if ($LASTEXITCODE -ne 0) { throw "ATIV FFmpeg runtime staging failed" }
Copy-Item (Join-Path $root "LICENSE") $publish
Copy-Item (Join-Path $root "THIRD_PARTY_NOTICES.md") $publish

python (Join-Path $root "script/ffmpeg_runtime.py") finish $ffmpegTarget --binary $publish --metadata (Join-Path $publish "ffmpeg-runtime")
if ($LASTEXITCODE -ne 0) { throw "Signed ATIV FFmpeg runtime recording failed" }

# Core licenses remain inside its immutable metadata tree; application licenses stay separate.
python (Join-Path $root "script/collect_licenses.py") (Join-Path $publish "licenses") --target $rustTarget
if ($LASTEXITCODE -ne 0) { throw "License collection failed" }
python (Join-Path $root "script/validate_package.py") $publish "windows-$label"
if ($LASTEXITCODE -ne 0) { throw "Packaged ATIV FFmpeg runtime validation failed" }

$managed = @(Get-ChildItem $publish -Recurse -File | ForEach-Object { [IO.Path]::GetRelativePath($publish, $_.FullName) })
$managed += 'portable-package-files.json'
ConvertTo-Json -InputObject $managed | Set-Content (Join-Path $publish 'portable-package-files.json')

$zip = Join-Path $packages "ATIV-$version-windows-$label.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "$publish/*" -DestinationPath $zip -CompressionLevel Optimal
Write-Output $zip
