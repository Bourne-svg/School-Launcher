import copy
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autofill import Tasks, matches, rule_for, rules, extension_id
from store import validate


def entry(site='hku'):
    rule=next(r for r in rules() if r['id']==site)
    return validate(dict(id=site,name='测试',url=rule['origin']+rule['paths'][0],kind=rule['kind'],account='test-user',password='test-only',email='test@example.edu'))


def bound(tasks,site='hku',tab=7):
    token=tasks.create(entry(site))
    base=dict(task=token,client='test-client-123456789',tab=tab)
    assert tasks.dispatch(dict(op='claim',**base))['ok']
    return base


def credentials(base,site='hku'):
    rule=next(r for r in rules() if r['id']==site)
    return dict(op='credentials',top=rule['origin']+rule['loginPaths'][0],frame=rule.get('frameOrigin',rule['origin'])+rule.get('framePaths',rule['loginPaths'])[0],frameId=3 if rule.get('frameOrigin') else 0,**base)


@pytest.mark.parametrize('site',[r['id'] for r in rules()])
def test_site_rules_and_one_time_fields(site):
    tasks=Tasks();base=bound(tasks,site)
    result=tasks.dispatch(credentials(base,site))
    assert result['ok']
    assert set(result['fields'])==set(next(r for r in rules() if r['id']==site)['fields'])
    assert tasks.jobs[base['task']]['fields']=={}
    assert not tasks.dispatch(credentials(base,site))['ok']
    assert tasks.dispatch(dict(op='result',code='filled',**base))['ok']
    assert tasks.status(base['task'])['status']=='filled'


def test_wrong_tab_and_duplicate_claim():
    tasks=Tasks();base=bound(tasks)
    assert not tasks.dispatch(dict(op='claim',**base))['ok']
    other=dict(base,tab=8)
    assert not tasks.dispatch(credentials(other))['ok']
    assert tasks.dispatch(credentials(base))['ok']


@pytest.mark.parametrize('bad',['https://evil.example/','http://tpgadmission.engg.hku.hk/','https://tpgadmission.engg.hku.hk.evil.example/','https://evil@tpgadmission.engg.hku.hk/'])
def test_wrong_origin_never_receives_fields(bad):
    tasks=Tasks();base=bound(tasks)
    message=credentials(base);message['top']=bad
    result=tasks.dispatch(message)
    assert not result['ok'] and 'fields' not in result
    assert tasks.jobs[base['task']]['fields']=={}


def test_frame_restrictions():
    tasks=Tasks();base=bound(tasks,'netease')
    msg=credentials(base,'netease');msg['frame']='https://evil.example/webzj/'
    assert not tasks.dispatch(msg)['ok']
    tasks=Tasks();base=bound(tasks)
    msg=credentials(base);msg['frameId']=2
    assert not tasks.dispatch(msg)['ok']


def test_expiry_cancellation_and_multi_tab():
    now=[100.0];tasks=Tasks(lambda:now[0])
    a=bound(tasks,tab=1);b=bound(tasks,tab=2)
    assert tasks.dispatch(credentials(a))['ok']
    assert tasks.dispatch(credentials(b))['ok']
    c=bound(tasks,'ntu',tab=3)
    now[0]+=121
    tasks.expire()
    assert tasks.status(c['task'])['status']=='expired'
    assert tasks.jobs[c['task']]['fields']=={}
    d=bound(tasks,'ntu',tab=4);tasks.cancel_entry('ntu')
    assert tasks.status(d['task'])['status']=='failed'


def test_invalid_urls_kinds_and_missing_fields():
    tasks=Tasks()
    value=entry();value['url']='file:///example'
    with pytest.raises(ValueError):tasks.create(value)
    value=entry();value['kind']='invalid'
    with pytest.raises(ValueError):tasks.create(value)
    value=entry();value['email']=''
    with pytest.raises(ValueError):tasks.create(value)


def test_unknown_ops_and_restarted_broker():
    tasks=Tasks();base=bound(tasks)
    assert not tasks.dispatch(dict(op='get_all',**base))['ok']
    assert not Tasks().dispatch(credentials(base))['ok']
    assert not tasks.dispatch(dict(op='result',code='filled',**base))['ok']


def test_manifest_permissions():
    manifest=json.loads(Path('extension/manifest.json').read_text(encoding='utf-8'))
    assert '<all_urls>' not in manifest['host_permissions']
    assert 'externally_connectable' not in manifest
    assert len(extension_id())==32
    assert manifest['manifest_version']==3


@pytest.mark.parametrize('url', [
    'https://sweb.hku.hk/tola/servlet/CreateUserScreen/loginForm',
    'https://github.com/Bourne-svg/School-Launcher',
    'http://localhost:8080/login',
])
@pytest.mark.parametrize('kind', ['password', 'application', 'email'])
def test_generic_task_origin_binding(url, kind):
    value = entry()
    value.update(url=url, kind=kind)
    tasks = Tasks()
    token = tasks.create(value)
    base = dict(task=token, client='test-client-123456789', tab=7)
    claim = tasks.dispatch(dict(op='claim', **base))
    assert claim['rule']['generic']
    assert 'test-only' not in json.dumps(claim)
    origin = claim['rule']['origin']
    result = tasks.dispatch(dict(op='credentials', top=origin+'/login', frame=origin+'/login', frameId=0, **base))
    assert result['ok']
    assert set(result['fields']) == set(claim['rule']['fields'])


@pytest.mark.parametrize('url,frame_id', [('https://evil.example/login', 0), ('https://example.edu/login', 1)])
def test_generic_rejects_foreign_origin_and_iframe(url, frame_id):
    value = entry()
    value.update(url='https://example.edu/start', kind='password')
    tasks = Tasks()
    token = tasks.create(value)
    base = dict(task=token, client='test-client-123456789', tab=7)
    tasks.dispatch(dict(op='claim', **base))
    result = tasks.dispatch(dict(op='credentials', top='https://example.edu/login', frame=url, frameId=frame_id, **base))
    assert not result['ok'] and 'fields' not in result


def test_generic_extension_permissions():
    manifest = json.loads(Path('extension/manifest.json').read_text(encoding='utf-8'))
    assert manifest['host_permissions'] == ['http://*/*', 'https://*/*']
    assert manifest['content_scripts'][0]['matches'] == manifest['host_permissions']
