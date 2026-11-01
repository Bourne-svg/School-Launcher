"""Build directly from the current repository and package a clean portable ZIP."""
import argparse
import hashlib
import shutil
import subprocess
import zipfile
from pathlib import Path

VERSION = '0.0.4'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work-dir', required=True)
    parser.add_argument('--python', default='python')
    parser.add_argument('--output-dir', help='Clean delivery directory, separate from build files')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = Path(args.work_dir).resolve()
    if work.exists():
        raise SystemExit('Use a new empty work directory; existing files will not be removed.')
    release = Path(args.output_dir).resolve() if args.output_dir else work / 'release'
    if release.exists():
        raise SystemExit('Use a new empty output directory; existing files will not be removed.')
    work.mkdir(parents=True)
    subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                    str(root / 'build.ps1'), '-Python', args.python, '-BuildRoot', str(work)], cwd=root, check=True)
    dist = work / 'dist/SchoolLauncher'
    release.mkdir(parents=True)
    delivery = release / 'SchoolLauncher'
    shutil.copytree(dist, delivery)
    output = release / f'SchoolLauncher-{VERSION}.zip'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(delivery.rglob('*')):
            if path.is_file():
                archive.write(path, Path('SchoolLauncher') / path.relative_to(delivery))
    digest = hashlib.file_digest(output.open('rb'), 'sha256').hexdigest()
    (release / 'SHA256SUMS.txt').write_text(digest + '  ' + output.name + '\n', encoding='ascii')
    print('Portable ZIP and SHA256SUMS.txt created:', release)


if __name__ == '__main__':
    main()
