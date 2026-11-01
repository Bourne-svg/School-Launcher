"""Export an explicit public source tree and build a clean portable ZIP."""
import argparse
import hashlib
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT_FILES = ('.gitignore', 'README.md', '使用说明.md', '验收记录.md',
              'requirements-lock.txt', 'build.ps1', 'app.py', 'autofill.py',
              'store.py', 'portable.py', 'native_bridge.py', 'native_host.py')
TOOLS = ('prepare.py', 'package_release.py', 'audit_release.py')
VERSION = '0.0.3'


def export_source(root, target):
    target.mkdir(parents=True, exist_ok=False)
    for name in ROOT_FILES:
        shutil.copy2(root / name, target / name)
    for folder, suffixes in [('ui', {'.html', '.js', '.css', '.ico'}),
                             ('extension', {'.html', '.js', '.css', '.png', '.json', '.txt'}),
                             ('tests', {'.py', '.mjs'})]:
        (target / folder).mkdir()
        for path in sorted((root / folder).iterdir()):
            if path.is_file() and path.suffix in suffixes:
                shutil.copy2(path, target / folder / path.name)
    (target / 'tools').mkdir()
    for name in TOOLS:
        shutil.copy2(root / 'tools' / name, target / 'tools' / name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work-dir', required=True)
    parser.add_argument('--python', default='python')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = Path(args.work_dir).resolve()
    if work.exists():
        raise SystemExit('Use a new empty work directory; existing files will not be removed.')
    source = work / 'source'
    export_source(root, source)
    subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                    str(source / 'build.ps1'), '-Python', args.python], cwd=source, check=True)
    dist = source / 'dist/SchoolLauncher'
    release = work / 'release'
    release.mkdir()
    output = release / f'SchoolLauncher-v{VERSION}-windows-x64.zip'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(dist.rglob('*')):
            if path.is_file():
                archive.write(path, Path('SchoolLauncher') / path.relative_to(dist))
    digest = hashlib.file_digest(output.open('rb'), 'sha256').hexdigest()
    (release / 'SHA256SUMS.txt').write_text(digest + '  ' + output.name + '\n', encoding='ascii')
    print('Portable ZIP and SHA256SUMS.txt created:', release)


if __name__ == '__main__':
    main()
