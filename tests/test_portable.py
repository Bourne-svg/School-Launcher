import json
import sys
import uuid
import winreg
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import autofill
import portable
from store import Vault


def test_profiles_and_saved_selection(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    state = tmp_path / 'Google/Chrome/User Data/Local State'
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({'profile': {'last_used': 'Profile 2', 'info_cache': {
        'Default': {'name': '默认'}, 'Profile 2': {'name': '工作'},
        'Profile 6': {'name': '其他'}, '../bad': {'name': 'bad'}}}}))
    assert autofill.profile_directory() == 'Profile 2'
    assert autofill.profile_directory('Default') == 'Default'
    with pytest.raises(ValueError):
        autofill.profile_directory('missing')
    with patch.object(app, 'Vault', return_value=Vault(tmp_path / 'vault')):
        api = app.API()
        assert api.get_state()['entries'] == []
        assert api.update_settings({'chrome_profile': 'Default'})['ok']
        assert app.API().get_state()['settings']['chrome_profile'] == 'Default'
        with patch.object(app, 'launch_chrome') as launch:
            api.check_extension()
            assert launch.call_args.kwargs['profile'] == 'Default'
        token = api._tasks.connection_check
        api._tasks.dispatch({'op': 'hello'})
        assert not api._tasks.connection_verified
        api._tasks.dispatch({'op': 'hello', 'check': 'wrong'})
        assert not api._tasks.connection_verified
        api._tasks.dispatch({'op': 'hello', 'check': token})
        assert api._tasks.connection_verified
        api.update_settings({'chrome_profile': 'Profile 2'})
        assert not api._tasks.connection_verified
        api._tasks.dispatch({'op': 'hello', 'check': token})
        assert not api._tasks.connection_verified


def test_registration_move_cleanup_and_shortcut_ownership(tmp_path, monkeypatch):
    registry = 'Software\\SchoolLauncherTests\\' + uuid.uuid4().hex
    monkeypatch.setattr(portable, 'REGISTRY', registry)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    root = tmp_path / '中文 directory'
    (root / 'NativeHost').mkdir(parents=True)
    (root / 'NativeHost/SchoolLauncherNative.exe').touch()
    executable = root / 'SchoolLauncher.exe'
    executable.touch()
    monkeypatch.setattr(sys, 'executable', str(executable))
    desktop = tmp_path / 'desktop.lnk'
    startup = tmp_path / 'startup.lnk'
    monkeypatch.setattr(portable, 'shortcut_path', lambda startup=False: tmp_path / ('startup.lnk' if startup else 'desktop.lnk'))
    try:
        assert portable.register_host(autofill.extension_id()) == dict(ok=True, moved=False)
        manifest = json.loads((root / 'native-host.json').read_text())
        assert manifest['path'] == str(root / 'NativeHost/SchoolLauncherNative.exe')
        assert manifest['allowed_origins'] == ['chrome-extension://' + autofill.extension_id() + '/']
        portable.create_desktop_shortcut()
        assert desktop.exists()
        # Another directory owns the registration: this copy must not remove it.
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, registry) as key:
            winreg.SetValueEx(key, '', 0, winreg.REG_SZ, str(tmp_path / 'other/native-host.json'))
        portable.cleanup_integration()
        assert portable.registered_manifest().endswith('other\\native-host.json')
        assert not desktop.exists()
        assert portable.register_host(autofill.extension_id())['moved']
        # A shortcut targeting another application must survive cleanup.
        import pythoncom
        from win32com.client import Dispatch
        pythoncom.CoInitialize()
        try:
            link = Dispatch('WScript.Shell').CreateShortCut(str(desktop))
            link.Targetpath = str(tmp_path / 'other.exe')
            link.save()
        finally:
            pythoncom.CoUninitialize()
        portable.cleanup_integration()
        assert desktop.exists()
        assert portable.registered_manifest() == ''
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, registry)
        except FileNotFoundError:
            pass


def test_missing_components_and_download_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'SchoolLauncher.exe'))
    with pytest.raises(ValueError, match='完整解压'):
        portable.register_host(autofill.extension_id())
    with patch.object(portable, 'webview_available', return_value=False), \
         patch.object(portable.ctypes.windll.user32, 'MessageBoxW', return_value=6), \
         patch.object(portable.webbrowser, 'open') as browser:
        assert not portable.ensure_webview()
        browser.assert_called_once_with(portable.WEBVIEW_URL)
    with patch.object(app, 'Vault', return_value=Vault(tmp_path / 'vault')), \
         patch.object(app, 'chrome_path', side_effect=RuntimeError):
        assert not app.API().get_connection_status()['chrome_installed']
