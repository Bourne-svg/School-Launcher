"""Local encrypted records. No credentials are bundled with the application."""
import copy
import json
import os
import re
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import win32crypt

DATA_DIR = Path(os.environ['LOCALAPPDATA']) / 'SchoolLauncher'


def validate(entry):
    name = str(entry.get('name', '')).strip()
    url = str(entry.get('url', '')).strip()
    if not name:
        raise ValueError('请填写名称')
    if url:
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or any(c.isspace() for c in url):
            raise ValueError('网址必须是完整的 HTTP 或 HTTPS 地址')
    kind = entry.get('kind', 'password')
    if kind not in ('password', 'application', 'email'):
        raise ValueError('请选择有效的登录方式')
    category = entry.get('category', '院校')
    if category not in ('院校', '工具'):
        raise ValueError('请选择有效的分类')
    return dict(id=str(entry.get('id') or uuid.uuid4()), name=name, url=url,
                category=category, kind=kind,
                account=str(entry.get('account', '')), password=str(entry.get('password', '')),
                email=str(entry.get('email', '')), note=str(entry.get('note', '')))


def import_markdown(path):
    text = Path(path).read_text(encoding='utf-8-sig').replace('**', '').replace(r'\_', '_')
    parts = re.split(r'【([^】]+)】', text)
    entries = []
    for i in range(1, len(parts), 2):
        name, body = parts[i].strip(), parts[i + 1]
        def field(label):
            match = re.search(r'^\s*' + label + r'[：:]([^\r\n]*)', body, re.M)
            return match.group(1).strip() if match else ''
        entry = dict(name=name, url=field('网址'), account=field('账号'), password=field('密码'),
                     email=field('邮箱'), kind='password', category='工具' if name in ('网易邮箱', '点头-算力云') else '院校', note='')
        if field('申请编号'):
            entry.update(kind='application', account=field('申请编号'), password='', note='使用申请编号和邮箱登录。')
        elif '发送登录链接' in body:
            emails = re.findall(r'[A-Za-z0-9_.+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', body)
            entry.update(kind='email', email=emails[0] if emails else '', account='', password='', note='输入邮箱后，前往邮箱打开系统发送的登录链接。')
        entries.append(validate(entry))
    if not entries:
        raise ValueError('文档中未找到条目')
    return entries


class Vault:
    def __init__(self, directory=DATA_DIR):
        self.directory = Path(directory)
        self.path = self.directory / 'vault.dat'
        self.backup = self.directory / 'vault.backup.dat'

    def read(self, backup=False):
        path = self.backup if backup else self.path
        raw = win32crypt.CryptUnprotectData(path.read_bytes(), None, None, None, 0)[1]
        data = json.loads(raw.decode('utf-8'))
        if data.get('version') != 1 or not isinstance(data.get('entries'), list):
            raise ValueError('数据格式无效')
        data['entries'] = [validate(e) for e in data['entries']]
        return data

    def write(self, data):
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
        encrypted = win32crypt.CryptProtectData(payload, 'SchoolLauncher', None, None, None, 0)
        self.directory.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        try:
            with temp.open('wb') as f:
                f.write(encrypted)
                f.flush()
                os.fsync(f.fileno())
            if self.path.exists():
                # Never replace a good backup with unreadable data.
                self.read()
                backup_temp = self.backup.with_suffix('.tmp')
                shutil.copyfile(self.path, backup_temp)
                os.replace(backup_temp, self.backup)
            os.replace(temp, self.path)
        finally:
            temp.unlink(missing_ok=True)

    def restore(self):
        data = self.read(backup=True)
        if self.path.exists():
            shutil.copyfile(self.path, self.directory / ('vault.damaged.' + uuid.uuid4().hex + '.dat'))
        temp = self.path.with_suffix('.restore')
        shutil.copyfile(self.backup, temp)
        os.replace(temp, self.path)
        return data


def new_data(entries=None):
    return dict(version=1, entries=entries or [], settings={'on_top': False, 'hidden': False})
