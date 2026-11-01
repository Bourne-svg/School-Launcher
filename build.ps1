param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$buildOriginalPath = $env:PATH
Push-Location $PSScriptRoot
try {
    # Conda keeps dependent DLLs (including ffi.dll for _ctypes) here.
    # Resolve the selected interpreter instead of relying on shell activation.
    $buildPythonPrefix = & $Python -c 'import sys; print(sys.prefix)'
    if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve Python environment' }
    $buildDllDirectory = Join-Path $buildPythonPrefix 'Library\bin'
    if (Test-Path -LiteralPath $buildDllDirectory) {
        $env:PATH = "$buildDllDirectory;$buildPythonPrefix;$env:PATH"
    }
    & $Python tools/prepare.py
    if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }
    & $Python -m PyInstaller --noconfirm --clean --windowed --onedir --name SchoolLauncher --icon ui/app.ico --add-data 'ui;ui' --add-data 'extension;extension' --hidden-import win32timezone --exclude-module pytest --exclude-module playwright app.py
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    & $Python -m PyInstaller --noconfirm --clean --console --onedir --name SchoolLauncherNative --add-data 'extension/manifest.json;extension' --add-data 'extension/sites.json;extension' --hidden-import win32timezone native_host.py
    if ($LASTEXITCODE -ne 0) { throw 'Native host build failed' }
    if (Test-Path -LiteralPath 'dist/SchoolLauncher/NativeHost') { throw 'Use a clean build directory: NativeHost already exists.' }
    Copy-Item -LiteralPath 'dist/SchoolLauncherNative' -Destination 'dist/SchoolLauncher/NativeHost' -Recurse -Force
    Copy-Item -LiteralPath '使用说明.md' -Destination 'dist/SchoolLauncher'
    & $Python tools/check_frozen.py dist/SchoolLauncher
    if ($LASTEXITCODE -ne 0) { throw 'Packaged startup checks failed' }
} finally {
    $env:PATH = $buildOriginalPath
    Pop-Location
}
