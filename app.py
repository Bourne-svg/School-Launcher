import copy
import ctypes
import json
import os
import sys
import threading
import time
import secrets
import webbrowser
import portable
from pathlib import Path

import pythoncom
import pystray
import webview
import win32api
import win32clipboard
import win32con
import win32event
from PIL import Image
from win32com.client import Dispatch

from store import DATA_DIR, Vault, new_data, validate
from autofill import Tasks, launch_chrome, extension_id, profile_directory, EXTENSION, rule_for, chrome_profiles, chrome_path
from native_bridge import Server

TITLE = '院校登录助手'
ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'ui'
MUTEX = r'Local\SchoolLauncher.Instance.' + os.environ.get('USERNAME', 'user')
EVENT = MUTEX + '.Show'


def startup_path():
    from win32com.shell import shell, shellcon
    return Path(shell.SHGetFolderPath(0, shellcon.CSIDL_STARTUP, None, 0)) / (TITLE + '.lnk')


def set_startup(enabled):
    path = startup_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    pythoncom.CoInitialize()
    shortcut = None
    try:
        shortcut = Dispatch('WScript.Shell').CreateShortCut(str(path))
        shortcut.Targetpath = sys.executable
        if not getattr(sys, 'frozen', False):
            shortcut.Arguments = '"' + str(Path(__file__).resolve()) + '"'
        shortcut.WorkingDirectory = str(Path(sys.executable).parent)
        shortcut.Description = TITLE
        shortcut.save()
    finally:
        shortcut = None
        pythoncom.CoUninitialize()


class API:
    def __init__(self):
        self._lock = threading.RLock()
        self._vault = Vault()
        self._error = None
        self._window = None
        self._tray = None
        self._quitting = False
        self._tray_ready = False
        self._tasks = Tasks()
        self._bridge = None
        self._integration = dict(ok=True, moved=False)
        try:
            self._data = self._vault.read() if self._vault.path.exists() else new_data()
        except Exception:
            self._data = None
            self._error = '本机数据无法解密或读取。请恢复上一份备份；当前文件会保留，不会被覆盖。'

    def _commit(self, data):
        self._vault.write(data)
        self._data = data

    def get_state(self):
        with self._lock:
            if self._error:
                return dict(ok=False, error=self._error, backup=self._vault.backup.exists())
            data = copy.deepcopy(self._data)
            data['settings']['startup'] = startup_path().exists()
            for entry in data['entries']:
                entry['autofill_supported'] = bool(rule_for(entry))
            return dict(ok=True, **data)

    def save_entry(self, entry):
        with self._lock:
            if self._error:
                return dict(ok=False, error=self._error)
            try:
                entry = validate(entry)
                data = copy.deepcopy(self._data)
                index = next((i for i, e in enumerate(data['entries']) if e['id'] == entry['id']), None)
                if index is None:
                    data['entries'].append(entry)
                else:
                    data['entries'][index] = entry
                self._commit(data)
                self._tasks.cancel_entry(entry['id'])
                return dict(ok=True)
            except ValueError as exc:
                return dict(ok=False, error=str(exc))
            except Exception:
                return dict(ok=False, error='保存失败，原数据已保留。请检查磁盘空间和文件权限。')

    def delete_entry(self, entry_id):
        with self._lock:
            if self._error:
                return dict(ok=False, error=self._error)
            try:
                data = copy.deepcopy(self._data)
                data['entries'] = [e for e in data['entries'] if e['id'] != entry_id]
                self._commit(data)
                self._tasks.cancel_entry(entry_id)
                return dict(ok=True)
            except Exception:
                return dict(ok=False, error='删除未保存，原数据已保留。')

    def _entry(self, entry_id):
        return next(e for e in self._data['entries'] if e['id'] == entry_id)

    def copy_field(self, entry_id, field):
        if field not in ('account', 'password', 'email', 'url'):
            return dict(ok=False, error='无法复制此字段')
        with self._lock:
            try:
                value = self._entry(entry_id)[field]
                if not value:
                    return dict(ok=False, error='请先补充内容')
                for attempt in range(5):
                    try:
                        win32clipboard.OpenClipboard()
                        break
                    except Exception:
                        if attempt == 4:
                            raise
                        time.sleep(.06)
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardText(value, win32con.CF_UNICODETEXT)
                finally:
                    win32clipboard.CloseClipboard()
                return dict(ok=True)
            except Exception:
                return dict(ok=False, error='剪贴板暂时不可用，请重试')

    def open_site(self, entry_id):
        try:
            with self._lock:
                entry = validate(self._entry(entry_id))
            if not entry['url']:
                return dict(ok=False, error='请先补充网址')
            self._launch(entry['url'])
            return dict(ok=True)
        except Exception:
            return dict(ok=False, error='无法打开网址，请检查地址或 Google Chrome 是否已安装。')

    def start_autofill(self, entry_id):
        try:
            if self._bridge and self._bridge.error:
                return dict(ok=False,error=self._bridge.error)
            with self._lock:
                entry = copy.deepcopy(self._entry(entry_id))
            self._tasks.cancel_entry(entry_id)
            task = self._tasks.create(entry)
            try:
                self._launch('chrome-extension://'+extension_id()+'/launch.html#task='+task)
            except Exception:
                self._tasks.cancel_entry(entry_id)
                raise
            return dict(ok=True,task=task)
        except ValueError as error:
            return dict(ok=False,error=str(error))
        except Exception:
            return dict(ok=False,error='无法启动 Chrome，请检查 Chrome 安装及扩展配置。')

    def get_fill_status(self, task):
        result=self._tasks.status(task)
        if result.get('status')=='connecting':
            result['message']='等待 Chrome 扩展连接；若未跳转，请在应用设置中配置扩展。'
        return result

    def _launch(self, url):
        selected = self._data['settings'].get('chrome_profile') if self._data else None
        launch_chrome(url, profile=selected)

    def get_connection_status(self):
        profiles, recent = chrome_profiles()
        error = self._integration.get('error') or (self._bridge.error if self._bridge else None)
        selected = self._data['settings'].get('chrome_profile') if self._data else None
        try:
            profile = profile_directory(selected)
        except ValueError as exc:
            profile, error = selected, str(exc)
        try:
            chrome_path()
            installed = True
        except RuntimeError:
            installed = False
        return dict(ok=True, connected=self._tasks.connection_verified,
                    profile=profile, profiles=profiles, chrome_installed=installed,
                    extension_path=str(EXTENSION), version='0.0.3', error=error,
                    moved=self._integration.get('moved', False))

    def open_extension_setup(self):
        try:
            # Chrome filters internal chrome:// URLs passed on its command line.
            # Open the chosen profile and let the user navigate via the omnibox.
            self._launch('about:blank')
        except Exception:
            return dict(ok=False, error='无法打开 Chrome，请安装 Chrome 并选择有效的配置。')
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText('chrome://extensions/', win32con.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            return dict(ok=True, message='已复制扩展页地址，请在 Chrome 中按 Ctrl+L、Ctrl+V，再按 Enter。')
        except Exception:
            return dict(ok=False, error='Chrome 已打开，但复制地址失败。请在地址栏输入 chrome://extensions/ 并回车。')

    def check_extension(self):
        try:
            with self._tasks.lock:
                self._tasks.connection_check = secrets.token_urlsafe(24)
                self._tasks.connection_verified = False
                check = self._tasks.connection_check
            self._launch('chrome-extension://' + extension_id() + '/launch.html#check=' + check)
            return dict(ok=True)
        except Exception:
            return dict(ok=False, error='无法打开 Chrome，请检查安装及所选配置。')

    def open_chrome_download(self):
        webbrowser.open(portable.CHROME_URL)
        return dict(ok=True)

    def open_extension_folder(self):
        try:
            os.startfile(str(EXTENSION))
            return dict(ok=True)
        except OSError:
            return dict(ok=False, error='无法打开目录，请完整解压程序。')

    def copy_extension_path(self):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(str(EXTENSION), win32con.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            return dict(ok=True)
        except Exception:
            return dict(ok=False, error='剪贴板暂时不可用，请重试。')

    def create_desktop_shortcut(self):
        try:
            portable.create_desktop_shortcut()
            return dict(ok=True)
        except Exception:
            return dict(ok=False, error='无法创建快捷方式，请检查桌面写入权限并使用正式程序。')

    def cleanup_integration(self):
        try:
            portable.cleanup_integration()
            self._tasks.connection_verified = False
            self._integration = dict(ok=False, error='连接已清理。退出后可删除解压目录；再次运行程序会重新注册连接。')
            return dict(ok=True)
        except Exception:
            return dict(ok=False, error='连接清理未完成，请检查权限。账号数据已保留。')

    def update_settings(self, changes):
        with self._lock:
            if self._error:
                return dict(ok=False, error=self._error)
            try:
                data = copy.deepcopy(self._data)
                if 'chrome_profile' in changes:
                    data['settings']['chrome_profile'] = profile_directory(str(changes['chrome_profile']))
                for key in ('hidden', 'on_top'):
                    if key in changes:
                        data['settings'][key] = bool(changes[key])
                self._commit(data)
                if 'chrome_profile' in changes:
                    with self._tasks.lock:
                        self._tasks.jobs.clear()
                        self._tasks.connection_check = None
                        self._tasks.connection_verified = False
                if 'on_top' in changes:
                    self._window.on_top = bool(changes['on_top'])
                if 'startup' in changes:
                    set_startup(bool(changes['startup']))
                return dict(ok=True)
            except Exception:
                return dict(ok=False, error='设置未能全部应用，请重试')

    def restore_backup(self):
        with self._lock:
            try:
                self._data = self._vault.restore()
                self._error = None
                return dict(ok=True)
            except Exception:
                return dict(ok=False, error='备份也无法读取。请保留数据目录，联系维护人员处理。')

    def show(self, *args):
        try:
            self._window.show()
            self._window.restore()
            # Briefly raising a non-pinned window also brings a second launch forward.
            self._window.on_top = True
            self._window.on_top = bool(self._data and self._data['settings'].get('on_top'))
        except Exception:
            pass

    def _geometry(self):
        if self._error or not self._window:
            return
        with self._lock:
            try:
                data = copy.deepcopy(self._data)
                data['settings']['geometry'] = dict(x=self._window.x, y=self._window.y, width=self._window.width, height=self._window.height)
                self._commit(data)
            except Exception:
                pass

    def _report_health(self):
        """Startup diagnostics contain counts/booleans only, never credential values."""
        healthy = False
        for _ in range(60):
            if self._quitting:
                return
            try:
                healthy = self._window.evaluate_js('typeof ready !== "undefined" && ready && document.querySelectorAll(".card").length')
                if self._data is not None and healthy == len(self._data['entries']) and self._tray_ready:
                    break
            except Exception:
                pass
            time.sleep(.25)
        try:
            self._vault.directory.mkdir(parents=True, exist_ok=True)
            report = dict(pid=os.getpid(), timestamp=time.time(), frozen=bool(getattr(sys, 'frozen', False)),
                          bridge_ready=bool(healthy is not False and self._data is not None and healthy == len(self._data['entries'])),
                          tray_ready=self._tray_ready, data_readable=self._error is None)
            (self._vault.directory / 'health.json').write_text(json.dumps(report), encoding='utf-8')
        except Exception:
            pass

    def close(self):
        self._geometry()
        if self._quitting:
            return True
        if self._tray_ready:
            self._window.hide()
            return False
        self._quitting = True
        return True

    def quit(self, *args):
        self._quitting = True
        self._geometry()
        if self._tray:
            self._tray.stop()
        self._window.destroy()


def main():
    mutex = win32event.CreateMutex(None, False, MUTEX)
    duplicate = win32api.GetLastError() == 183
    event = win32event.CreateEvent(None, False, False, EVENT)
    quit_event = win32event.CreateEvent(None, False, False, EVENT+'.Quit')
    if duplicate:
        win32event.SetEvent(quit_event if '--quit' in sys.argv else event)
        return
    if '--quit' in sys.argv:
        return
    if not portable.ensure_webview():
        return
    api = API()
    try:
        api._integration = portable.register_host(extension_id())
    except Exception as exc:
        api._integration = dict(ok=False, error=str(exc) if isinstance(exc, ValueError) else '浏览器连接注册失败，请将完整程序解压到可写入的目录后重试。')
    if api._data is not None and not api._data['settings'].get('chrome_profile'):
        data = copy.deepcopy(api._data)
        data['settings']['chrome_profile'] = profile_directory()
        try:
            api._commit(data)
        except Exception:
            api._integration = dict(ok=False, error='无法保存首次配置，请检查数据目录权限。')
    settings = api._data['settings'] if api._data else {}
    geometry = settings.get('geometry', {})
    width = max(640, min(geometry.get('width', 1180), win32api.GetSystemMetrics(0)))
    height = max(480, min(geometry.get('height', 800), win32api.GetSystemMetrics(1) - 48))
    x, y = geometry.get('x'), geometry.get('y')
    # Recover windows formerly positioned on a disconnected monitor.
    if x is not None and not any(r['Monitor'][0] <= x < r['Monitor'][2] - 80 and r['Monitor'][1] <= y < r['Monitor'][3] - 80 for r in [win32api.GetMonitorInfo(m[0]) for m in win32api.EnumDisplayMonitors()]):
        x = y = None
    api._window = webview.create_window(TITLE, str(ASSETS / 'index.html'), js_api=api,
                                      width=width, height=height, x=x, y=y, min_size=(640, 480),
                                      background_color='#F7F8F6', on_top=settings.get('on_top', False), text_select=True)
    api._window.events.closing += api.close

    def ready():
        api._bridge=Server(api._tasks.dispatch)
        api._bridge.start()
        icon = Image.open(ASSETS / 'app.ico')
        api._tray = pystray.Icon('SchoolLauncher', icon, TITLE, menu=pystray.Menu(
            pystray.MenuItem('显示院校登录助手', api.show, default=True), pystray.MenuItem('退出', api.quit)))
        def setup(tray):
            tray.visible = True
            api._tray_ready = True
        threading.Thread(target=lambda: api._tray.run(setup), daemon=True).start()
        threading.Thread(target=api._report_health, daemon=True).start()
        while not api._quitting:
            api._tasks.expire()
            if win32event.WaitForSingleObject(quit_event,0)==win32event.WAIT_OBJECT_0:
                api.quit()
                break
            if win32event.WaitForSingleObject(event, 500) == win32event.WAIT_OBJECT_0:
                api.show()

    webview.start(ready, gui='edgechromium', debug=False, private_mode=True)
    api._quitting = True
    if api._tray:
        api._tray.stop()
    win32api.CloseHandle(event)
    win32api.CloseHandle(quit_event)
    win32api.CloseHandle(mutex)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        # Import the actual renderer and exercise native dependencies without
        # opening a window, accessing the vault, or registering the native host.
        import webview.platforms.edgechromium
        import win32crypt
        sample = b'SchoolLauncher startup check'
        encrypted = win32crypt.CryptProtectData(sample, '', None, None, None, 0)
        assert win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1] == sample
        assert ctypes.CDLL('kernel32.dll')
        assert (ASSETS / 'index.html').is_file()
        Path(sys.argv[2]).write_text(json.dumps(dict(ok=True, version=Tasks().dispatch({'op': 'hello'})['version'])), encoding='utf-8')
        sys.exit(0)
    try:
        main()
    except Exception:
        ctypes.windll.user32.MessageBoxW(0, '应用启动失败。请检查 WebView2 运行时是否可用，或联系维护人员。您的本机数据不会被覆盖。', TITLE, 0x10)
