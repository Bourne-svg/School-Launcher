param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & $Python tools/prepare.py
    if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }
    & $Python -m PyInstaller --noconfirm --clean --windowed --onedir --name SchoolLauncher --icon ui/app.ico --add-data 'ui;ui' --add-data 'extension;extension' --hidden-import win32timezone --exclude-module pytest --exclude-module playwright app.py
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    & $Python -m PyInstaller --noconfirm --clean --console --onedir --name SchoolLauncherNative --add-data 'extension/manifest.json;extension' --add-data 'extension/sites.json;extension' --hidden-import win32timezone native_host.py
    if ($LASTEXITCODE -ne 0) { throw 'Native host build failed' }
    if (Test-Path -LiteralPath 'dist/SchoolLauncher/NativeHost') { throw 'Use a clean build directory: NativeHost already exists.' }
    Copy-Item -LiteralPath 'dist/SchoolLauncherNative' -Destination 'dist/SchoolLauncher/NativeHost' -Recurse -Force
    Copy-Item -LiteralPath '使用说明.md' -Destination 'dist/SchoolLauncher'
} finally { Pop-Location }
