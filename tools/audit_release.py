"""Scan public files and embedded Python archives without printing secret values."""
import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', nargs='+')
    parser.add_argument('--private-vault', help='Optional local vault for in-memory exact secret matching')
    args = parser.parse_args()
    needles = []
    if args.private_vault:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from store import Vault
        data = Vault(Path(args.private_vault)).read()
        for entry in data['entries']:
            for field in ('account', 'password', 'email', 'note'):
                value = entry.get(field, '')
                # These are fixed help messages from the legacy importer, not personal notes.
                generic_notes = ('使用申请编号和邮箱登录。', '输入邮箱后，前往邮箱打开系统发送的登录链接。')
                if field == 'note' and value in generic_notes:
                    continue
                if len(value) >= 4:
                    needles.extend([value.encode('utf-8'), value.encode('utf-16le')])
    findings = set()
    count = 0

    def scan(name, raw):
        nonlocal count
        if raw is None:
            return
        count += 1
        if any(value in raw for value in needles):
            findings.add((name, 'private-value-match'))
        # Conda's vendor PDB paths use anonymous CI task IDs; they are not a user's home.
        for readable in (raw, raw.decode('utf-16le', errors='ignore').encode('utf-8')):
            for match in re.finditer(rb'[A-Za-z]:[\\/]+Users[\\/]+([^\\/\x00\r\n ]+)', readable):
                user = match.group(1)
                vendor_binary = name.endswith(('.pyd', '.dll')) and re.fullmatch(rb'task_[0-9]+', user)
                if user not in (b'Public', b'Default') and not vendor_binary:
                    findings.add((name, 'user-home-path'))
        if b'-----BEGIN ' + b'PRIVATE KEY-----' in raw or b'-----BEGIN RSA ' + b'PRIVATE KEY-----' in raw:
            findings.add((name, 'private-key'))
        if re.search(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})', raw):
            findings.add((name, 'access-token'))

    def inspect(path, label):
        raw = path.read_bytes()
        scan(label, raw)
        if path.suffix in ('.zip', '.pyz') and zipfile.is_zipfile(path):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for item in archive.infolist():
                    if not item.is_dir():
                        scan(label + '/' + item.filename, archive.read(item))
        if path.suffix == '.exe' and path.name in ('SchoolLauncher.exe', 'SchoolLauncherNative.exe'):
            from PyInstaller.archive.readers import CArchiveReader
            archive = CArchiveReader(str(path))
            for name, item in archive.toc.items():
                payload = archive.extract(name)
                if payload:
                    scan(label + '/' + name, payload)
                if item[-1] == 'z':
                    pyz = archive.open_embedded_archive(name)
                    for module in pyz.toc:
                        scan(label + '/PYZ/' + module, pyz.extract(module, raw=True))

    for supplied in args.paths:
        root = Path(supplied)
        for path in sorted(root.rglob('*')) if root.is_dir() else [root]:
            if not path.is_file() or any(part in ('.git', '__pycache__', '.pytest_cache') for part in path.parts):
                continue
            label = str(path.relative_to(root)) if root.is_dir() else path.name
            if path.name.startswith('vault.') or path.suffix in ('.dat', '.log', '.lnk', '.pem', '.key'):
                findings.add((label, 'excluded-file-type'))
            inspect(path, label)
    print(json.dumps(dict(scanned=count, findings=[dict(path=p, kind=k) for p, k in sorted(findings)]), ensure_ascii=False))
    raise SystemExit(bool(findings))


if __name__ == '__main__':
    main()
