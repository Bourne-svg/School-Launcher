"""Run both packaged executables without Python/Conda DLL search paths."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    dist = Path(sys.argv[1]).resolve()
    env = {k.upper(): v for k, v in os.environ.items()
           if not k.upper().startswith(('CONDA', 'PYTHON', '_PYI'))}
    windows = Path(env['SYSTEMROOT'])
    env['PATH'] = os.pathsep.join([str(windows / 'System32'), str(windows)])
    version = json.loads((dist / '_internal/extension/manifest.json').read_text(encoding='utf-8'))['version']
    with tempfile.TemporaryDirectory(prefix='SchoolLauncher-check-') as temporary:
        report = Path(temporary) / 'startup.json'
        options = dict(env=env, cwd=temporary, check=True, timeout=45,
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        subprocess.run([str(dist / 'SchoolLauncher.exe'), '--self-test', str(report)], **options)
        assert json.loads(report.read_text(encoding='utf-8')) == dict(ok=True, version=version)
        result = subprocess.run([str(dist / 'NativeHost/SchoolLauncherNative.exe'), '--self-test'], **options)
        assert json.loads(result.stdout) == dict(ok=True, version=version)
    print('PASS: packaged app renderer, ctypes, DPAPI and native host with system-only PATH')


if __name__ == '__main__':
    main()
