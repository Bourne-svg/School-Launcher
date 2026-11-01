"""Current-user integration for the portable Windows distribution."""
import ctypes
import json
import os
import sys
import webbrowser
import winreg
from pathlib import Path

import pythoncom
from win32com.client import Dispatch
from win32com.shell import shell, shellcon

TITLE = '院校登录助手'
REGISTRY = r'Software\Google\Chrome\NativeMessagingHosts\cn.schoollauncher.autofill'
WEBVIEW_URL = 'https://developer.microsoft.com/microsoft-edge/webview2/'
CHROME_URL = 'https://www.google.com/chrome/'


def program_dir():
    return Path(sys.executable).resolve().parent


def same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def shortcut_path(startup=False):
    folder = shellcon.CSIDL_STARTUP if startup else shellcon.CSIDL_DESKTOPDIRECTORY
    return Path(shell.SHGetFolderPath(0, folder, None, 0)) / (TITLE + '.lnk')


def create_desktop_shortcut():
    if not getattr(sys, 'frozen', False):
        raise ValueError('请在解压后的正式程序中创建桌面快捷方式。')
    pythoncom.CoInitialize()
    try:
        link = Dispatch('WScript.Shell').CreateShortCut(str(shortcut_path()))
        link.Targetpath = sys.executable
        link.WorkingDirectory = str(program_dir())
        link.IconLocation = sys.executable + ',0'
        link.Description = TITLE
        link.save()
    finally:
        pythoncom.CoUninitialize()


def registered_manifest():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY) as key:
            return winreg.QueryValueEx(key, '')[0]
    except FileNotFoundError:
        return ''


def register_host(extension_id):
    if not getattr(sys, 'frozen', False):
        return dict(ok=True, moved=False)
    root = program_dir()
    host = root / 'NativeHost' / 'SchoolLauncherNative.exe'
    if not host.is_file():
        raise ValueError('浏览器组件不完整，请完整解压下载包，不要单独移动 EXE。')
    manifest = root / 'native-host.json'
    previous = registered_manifest()
    payload = dict(name='cn.schoollauncher.autofill', description='SchoolLauncher local autofill bridge',
                   path=str(host), type='stdio', allowed_origins=['chrome-extension://' + extension_id + '/'])
    temporary = manifest.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload), encoding='utf-8')
    os.replace(temporary, manifest)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY) as key:
        winreg.SetValueEx(key, '', 0, winreg.REG_SZ, str(manifest))
    return dict(ok=True, moved=bool(previous and not same_path(previous, manifest)))


def cleanup_integration():
    if not getattr(sys, 'frozen', False):
        raise ValueError('请在正式程序中清理连接。')
    manifest = program_dir() / 'native-host.json'
    previous = registered_manifest()
    if previous and same_path(previous, manifest):
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REGISTRY)
    pythoncom.CoInitialize()
    try:
        for path in (shortcut_path(), shortcut_path(True)):
            if path.exists():
                link = Dispatch('WScript.Shell').CreateShortCut(str(path))
                if same_path(link.Targetpath, sys.executable):
                    path.unlink()
    finally:
        pythoncom.CoUninitialize()
    manifest.unlink(missing_ok=True)


def webview_available():
    guid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, 'SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\' + guid,
                                    0, winreg.KEY_READ | view) as key:
                    version = winreg.QueryValueEx(key, 'pv')[0]
                    if int(version.split('.')[0]) >= 86:
                        return True
            except (OSError, ValueError, TypeError):
                pass
    return False


def ensure_webview():
    if webview_available():
        return True
    answer = ctypes.windll.user32.MessageBoxW(0,
        '需要 Microsoft Edge WebView2 运行时才能显示界面。是否打开微软官方下载页面？安装后请重新启动本程序。', TITLE, 0x24)
    if answer == 6:
        webbrowser.open(WEBVIEW_URL)
    return False
