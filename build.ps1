param([string]$Python = 'python', [string]$BuildRoot = '')
$ErrorActionPreference = 'Stop'
$buildOriginalPath = $env:PATH
Push-Location $PSScriptRoot
try {
    if (-not $BuildRoot) { $BuildRoot = $PSScriptRoot }
    $BuildRoot = [IO.Path]::GetFullPath($BuildRoot)
    $buildDist = Join-Path $BuildRoot 'dist'
    $buildWork = Join-Path $BuildRoot 'build'
    $buildSpec = Join-Path $BuildRoot 'spec'
    New-Item -ItemType Directory -Path $buildSpec -Force | Out-Null
    $buildOutput = Join-Path $buildDist 'SchoolLauncher'
    $buildNative = Join-Path $buildDist 'SchoolLauncherNative'
    if (Test-Path -LiteralPath $buildOutput) { throw 'Use a clean build directory: program output already exists.' }
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
    & $Python -m PyInstaller --noconfirm --clean --distpath $buildDist --workpath $buildWork --specpath $buildSpec --windowed --onedir --name SchoolLauncher --icon "$PSScriptRoot/ui/app.ico" --add-data "$PSScriptRoot/ui;ui" --add-data "$PSScriptRoot/extension;extension" --hidden-import win32timezone --exclude-module pytest --exclude-module playwright app.py
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    & $Python -m PyInstaller --noconfirm --clean --distpath $buildDist --workpath $buildWork --specpath $buildSpec --console --onedir --name SchoolLauncherNative --add-data "$PSScriptRoot/extension/manifest.json;extension" --add-data "$PSScriptRoot/extension/sites.json;extension" --hidden-import win32timezone native_host.py
    if ($LASTEXITCODE -ne 0) { throw 'Native host build failed' }
    Copy-Item -LiteralPath $buildNative -Destination (Join-Path $buildOutput 'NativeHost') -Recurse -Force
    Copy-Item -LiteralPath '使用说明.md' -Destination $buildOutput
    & $Python tools/check_frozen.py $buildOutput
    if ($LASTEXITCODE -ne 0) { throw 'Packaged startup checks failed' }
} finally {
    $env:PATH = $buildOriginalPath
    Pop-Location
}
