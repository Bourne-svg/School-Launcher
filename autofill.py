"""Chrome launch and short-lived, tab-bound tasks. No credential persistence."""
import copy
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import winreg
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
EXTENSION = ROOT / 'extension'
HOST_NAME = 'cn.schoollauncher.autofill'


def extension_id():
    import base64, hashlib
    key = json.loads((EXTENSION / 'manifest.json').read_text(encoding='utf-8'))['key']
    return ''.join(chr(ord('a') + int(c, 16)) for c in hashlib.sha256(base64.b64decode(key)).hexdigest()[:32])


def rules():
    return json.loads((EXTENSION / 'sites.json').read_text(encoding='utf-8'))


def matches(url, origin, paths):
    try:
        p = urlsplit(url)
        actual = p.scheme + '://' + p.netloc
        return actual == origin and not p.username and any(p.path == x or (x.endswith('/') and x != '/' and p.path.startswith(x)) for x in paths)
    except ValueError:
        return False


def rule_for(entry):
    return next((r for r in rules() if r['kind'] == entry['kind'] and matches(entry['url'], r['origin'], r['paths'])), None)


def chrome_path():
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe') as key:
                path = Path(winreg.QueryValueEx(key, '')[0])
                if path.is_file():
                    return path
        except OSError:
            pass
    for base in (os.environ.get('PROGRAMFILES',''), os.environ.get('PROGRAMFILES(X86)',''), os.environ['LOCALAPPDATA']):
        path = Path(base) / 'Google/Chrome/Application/chrome.exe'
        if path.is_file():
            return path
    raise RuntimeError('未找到 Google Chrome，请先安装 Chrome。')


def chrome_profiles():
    local = Path(os.environ['LOCALAPPDATA']) / 'Google/Chrome/User Data/Local State'
    try:
        data = json.loads(local.read_text(encoding='utf-8'))['profile']
        profiles = data.get('info_cache', {})
        valid = [dict(id=k, name=str(v.get('name', k))) for k, v in profiles.items()
                 if k == 'Default' or (k.startswith('Profile ') and k[8:].isdigit())]
        if valid:
            return valid, data.get('last_used', 'Default')
    except (OSError, KeyError, ValueError, TypeError):
        pass
    return [dict(id='Default', name='默认配置')], 'Default'


def profile_directory(selected=None):
    profiles, recent = chrome_profiles()
    ids = [p['id'] for p in profiles]
    if selected:
        if selected not in ids:
            raise ValueError('所选 Chrome 配置已不存在，请在应用设置中重新选择。')
        return selected
    return recent if recent in ids else ids[0]


def launch_chrome(url, profile=None):
    subprocess.Popen([str(chrome_path()), '--profile-directory=' + profile_directory(profile), url],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Tasks:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.RLock()
        self.jobs = {}
        self.last_seen = -1e9
        self.connection_check = None
        self.connection_verified = False

    def expire(self):
        with self.lock:
            now = self.clock()
            for token, job in list(self.jobs.items()):
                if now > job['expires'] and job['status'] not in ('filled','failed','expired'):
                    job.update(status='expired', message='填入任务已超时，请重新点击。', fields={})
                if now > job['expires'] + 600:
                    del self.jobs[token]

    def create(self, entry):
        rule = rule_for(entry)
        if not rule:
            raise ValueError('该网址或登录方式尚未适配，请使用“仅打开网站”和复制。')
        fields = {k: entry.get(k, '') for k in rule['fields']}
        if not all(fields.values()):
            raise ValueError('请先补充此条目的登录信息。')
        with self.lock:
            self.expire()
            token = secrets.token_urlsafe(32)
            self.jobs[token] = dict(entry_id=entry['id'], url=entry['url'], rule=rule, fields=fields,
                                    expires=self.clock()+120, status='connecting', message='等待浏览器连接', binding=None, delivered=False)
            return token

    def status(self, token):
        with self.lock:
            self.expire()
            job = self.jobs.get(token)
            if not job:
                return dict(ok=False,error='任务不存在，请重新点击。')
            return dict(ok=True,status=job['status'],message=job['message'])

    def cancel_entry(self, entry_id):
        with self.lock:
            for job in self.jobs.values():
                if job['entry_id']==entry_id and job['status'] not in ('filled','failed','expired'):
                    job.update(status='failed',message='条目已修改，请重新发起填入。',fields={})

    def dispatch(self, message):
        with self.lock:
            self.expire()
            self.last_seen = self.clock()
            op = message.get('op')
            if op == 'hello':
                if self.connection_check and secrets.compare_digest(str(message.get('check', '')), self.connection_check):
                    self.connection_verified = True
                return dict(ok=True,version='0.0.2')
            token = message.get('task')
            job = self.jobs.get(token)
            if not job or job['status'] in ('filled','failed','expired'):
                return dict(ok=False,error='任务已结束或过期，请重新点击助手。')
            binding = (message.get('client'), message.get('tab'))
            if not isinstance(binding[0], str) or len(binding[0]) < 16 or not isinstance(binding[1], int) or binding[1]<0:
                return dict(ok=False,error='无效的浏览器任务')
            if op == 'claim':
                if job['binding'] is not None:
                    return dict(ok=False,error='任务已被领取，请重新点击助手。')
                job.update(binding=binding,status='waiting',message='等待登录表单')
                return dict(ok=True,url=job['url'],site=job['rule']['id'],ttl=120)
            if job['binding'] != binding:
                return dict(ok=False,error='任务与当前标签页不匹配')
            if op == 'credentials':
                rule=job['rule']
                top=message.get('top',''); frame=message.get('frame','')
                valid_top=matches(top,rule['origin'],rule['loginPaths'])
                valid_frame=matches(frame,rule.get('frameOrigin',rule['origin']),rule.get('framePaths',rule['loginPaths']))
                if not valid_top or not valid_frame or (not rule.get('frameOrigin') and message.get('frameId')!=0):
                    job.update(status='failed',message='页面地址不匹配，已停止填入。',fields={})
                    return dict(ok=False,error=job['message'])
                if job['delivered']:
                    return dict(ok=False,error='资料已经交付，请重新点击助手。')
                values=job['fields']
                job.update(delivered=True,fields={},status='filling',message='正在填入')
                return dict(ok=True,fields=values)
            if op == 'result':
                code=message.get('code')
                messages={'filled':'已填入，请在网页中确认并点击登录。','conflict':'网页已有不同内容，未覆盖，请手动处理。','ambiguous':'登录输入框匹配不唯一，未填入。','changed':'页面或表单发生变化，请重新点击。','timeout':'未找到登录表单，请手动打开登录区域后重试。','navigation':'页面跳转到未允许的地址，已停止。','closed':'标签页已关闭。','error':'未能完成填入，请重试或使用复制。'}
                if code not in messages or (code=='filled' and not job['delivered']):
                    return dict(ok=False,error='无效的任务结果')
                job.update(status='filled' if code=='filled' else 'failed',message=messages[code],fields={})
                return dict(ok=True)
            return dict(ok=False,error='不支持的操作')
