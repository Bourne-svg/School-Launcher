"""Exercise the actual WebView2 bridge and tray with an isolated synthetic vault."""
import sys
import tempfile
import threading
import time
import traceback
import faulthandler
faulthandler.dump_traceback_later(25, repeat=False)
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import native_bridge
original_pipe=native_bridge.pipe_name()
native_bridge.pipe_name=lambda:original_pipe+'.NativeTest'
from store import Vault, new_data, validate

temporary = tempfile.TemporaryDirectory()
vault = Vault(temporary.name)
vault.write(new_data([validate(dict(name='运行验证',url='https://example.edu',account='demo',password='test-only'))]))
app.Vault = lambda: vault
app.startup_path = lambda: Path(temporary.name) / 'startup-test.lnk'
app.MUTEX += '.NativeTest'
app.EVENT += '.NativeTest'
original_api = app.API
original_start = app.webview.start
instance = None
failures=[]

def create_api():
    global instance
    instance = original_api()
    return instance

def test_worker():
    try:
        deadline=time.time()+35
        while time.time()<deadline:
            if instance and instance._window and instance._tray_ready:
                try:
                    if instance._window.evaluate_js('document.querySelectorAll(".card").length')==1:
                        break
                except Exception:
                    pass
            time.sleep(.3)
        else:
            raise AssertionError('Native bridge/tray did not initialize')
        assert instance._window.evaluate_js('document.querySelector(".card h2").textContent')=='运行验证'
        print('Native UI loaded', flush=True)
        assert instance.update_settings({'on_top':True})['ok']
        assert instance._window.on_top
        print('Native pinned', flush=True)
        assert instance.update_settings({'startup':True})['ok']
        print('Startup enabled', flush=True)
        assert app.startup_path().exists()
        assert instance.update_settings({'startup':False})['ok']
        print('Startup disabled', flush=True)
        assert not app.startup_path().exists()
        assert instance.update_settings({'hidden':True})['ok']
        instance._window.evaluate_js('refresh()')
        time.sleep(.4)
        assert instance._window.evaluate_js('document.querySelector(".field-value").textContent')=='••••••••'
        assert instance.close() is False
        time.sleep(.2)
        instance.show()
        assert instance.update_settings({'on_top':False})['ok']
        instance._window.resize(750,550)
        time.sleep(.3)
        instance._geometry()
        assert vault.read()['settings']['geometry']['width']==750
        print('NATIVE PASS: WebView2 bridge, encrypted settings, tray ready, hide/show, pin/unpin, geometry persistence.')
    except Exception:
        failures.append(traceback.format_exc())
    finally:
        if instance and instance._window:
            instance.quit()

app.API=create_api
threading.Thread(target=test_worker,daemon=True).start()
app.main()
temporary.cleanup()
if failures:
    print('\n'.join(failures))
    raise SystemExit(1)
