import copy
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import Vault, import_markdown, new_data, validate


def record(**kwargs):
    return validate(dict(name='测试大学', url='https://example.edu/login', account='demo@example.edu', password='Fake-Only-123!', **kwargs))


def test_vault_roundtrip_and_backup(tmp_path):
    vault = Vault(tmp_path)
    data = new_data([record()])
    vault.write(data)
    assert vault.read() == data
    assert b'Fake-Only-123!' not in vault.path.read_bytes()
    second = copy.deepcopy(data)
    second['entries'][0]['password'] = 'Updated-Fake-Only'
    vault.write(second)
    assert Vault(tmp_path).read() == second
    assert vault.read(backup=True) == data
    vault.path.write_bytes(b'corrupt')
    with pytest.raises(Exception):
        vault.read()
    assert vault.restore() == data
    assert list(tmp_path.glob('vault.damaged.*.dat'))


def test_failed_replace_preserves_current(tmp_path):
    vault = Vault(tmp_path)
    data = new_data([record()])
    vault.write(data)
    original = vault.path.read_bytes()
    with patch('store.os.replace', side_effect=PermissionError):
        with pytest.raises(PermissionError):
            vault.write(new_data())
    assert vault.path.read_bytes() == original
    assert vault.read() == data


def test_corrupt_data_never_overwritten(tmp_path):
    vault = Vault(tmp_path)
    vault.path.write_bytes(b'broken')
    with pytest.raises(Exception):
        vault.write(new_data())
    assert vault.path.read_bytes() == b'broken'


@pytest.mark.parametrize('url',['javascript:alert(1)','file:///C:/data','https://','https://user:pass@example.edu','https://exa mple.edu'])
def test_reject_bad_url(url):
    with pytest.raises(ValueError):
        validate(dict(name='Test',url=url))


def test_import_special_fields(tmp_path):
    document = tmp_path / 'source.md'
    document.write_text('**【测试学校】**\n网址：https://example.edu/login\\_email\n账号：Case@Example.edu\n密码：Fake!\n【申请学校】\n申请编号：001234\n邮箱：Case@Example.edu\n【链接学校】\n系统发送登录链接，使用（Case@Example.edu）\n【空白学校】\n先留空\n',encoding='utf-8')
    entries = import_markdown(document)
    assert len(entries) == 4
    assert entries[0]['url'].endswith('login_email')
    assert entries[0]['account'] == 'Case@Example.edu'
    assert entries[1]['account'] == '001234' and entries[1]['kind'] == 'application'
    assert entries[2]['email'] == 'Case@Example.edu' and entries[2]['kind'] == 'email'
    assert entries[3]['url'] == ''


def test_backend_crud_copy_and_open(tmp_path):
    import app
    import win32clipboard
    vault = Vault(tmp_path)
    with patch.object(app, 'Vault', return_value=vault):
        api = app.API()
    entry = record()
    assert api.save_entry(entry)['ok']
    assert [{k:v for k,v in e.items() if k!='autofill_supported'} for e in api.get_state()['entries']] == [entry]
    # Preserve existing clipboard text while testing a synthetic value.
    win32clipboard.OpenClipboard()
    try:
        previous = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT) if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT) else None
    finally:
        win32clipboard.CloseClipboard()
    try:
        assert api.copy_field(entry['id'], 'password')['ok']
        win32clipboard.OpenClipboard()
        try:
            assert win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT) == entry['password']
        finally:
            win32clipboard.CloseClipboard()
    finally:
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            if previous is not None:
                win32clipboard.SetClipboardText(previous, win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
    with patch.object(app, 'launch_chrome') as opened:
        assert api.open_site(entry['id'])['ok']
        opened.assert_called_once_with(entry['url'], profile=None)
    assert api.delete_entry(entry['id'])['ok']
    assert vault.read()['entries'] == []


def test_startup_shortcut_toggle(tmp_path):
    import app
    import pythoncom
    from win32com.client import Dispatch
    link = tmp_path / 'startup-test.lnk'
    with patch.object(app, 'startup_path', return_value=link):
        app.set_startup(True)
        assert link.exists()
        pythoncom.CoInitialize()
        try:
            shortcut = Dispatch('WScript.Shell').CreateShortCut(str(link))
            assert Path(shortcut.Targetpath).resolve() == Path(sys.executable).resolve()
            shortcut = None
        finally:
            pythoncom.CoUninitialize()
        app.set_startup(False)
        assert not link.exists()


def test_api_failed_save_retains_memory(tmp_path):
    import app
    vault = Vault(tmp_path)
    with patch.object(app, 'Vault', return_value=vault):
        api = app.API()
    with patch.object(vault, 'write', side_effect=OSError):
        assert api.save_entry(record())['ok'] is False
    assert api.get_state()['entries'] == []
