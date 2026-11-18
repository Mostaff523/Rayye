import time
import pytest
from fastapi.testclient import TestClient
from app import main as m

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'DB',str(tmp_path/'test.db'))
    monkeypatch.setattr(m,'TOKEN','test-token')
    m.ACTIVE.clear()
    with TestClient(m.app) as c:
        c.headers['Authorization']='Bearer test-token'
        yield c
    m.ACTIVE.clear()


def feed(c,zone=1,device='esp32-1',sensor='s1',value=20):
    return c.post('/telemetry',json={'zone_id':zone,'node_id':device,'sensor_id':sensor,'moisture':value})


def test_seed_and_security(client):
    assert len(client.get('/zones').json())==2
    assert len(client.get('/devices').json())==3
    assert client.get('/zones',headers={'Authorization':'Bearer bad'}).status_code==401
    assert client.get('/setup').json()['location']=='Port Said, Egypt'
    assert client.get('/health').json()['hardware']=='simulated'


def test_simultaneous_and_capacity(client):
    assert client.post('/zones/1/manual',json={}).status_code==200
    assert client.post('/zones/2/manual',json={}).status_code==200
    assert len(client.get('/status').json()['active'])==2
    extra=client.post('/zones',json={'name':'zone 3'}).json()['id']
    assert client.post(f'/zones/{extra}/manual',json={}).status_code==409
    assert client.post('/stop').json()['pump_on'] is False


def test_threshold_stop_and_manual_return(client):
    assert feed(client).status_code==201
    z=client.get('/zones').json()[0]
    body={'name':z['name'],'mode':'auto'}
    assert client.put('/zones/1',json=body).status_code==200
    m.tick()
    assert m.ACTIVE[1]['source']=='auto'
    assert feed(client,value=70).status_code==201
    m.tick()
    assert 1 not in m.ACTIVE
    assert client.get('/zones').json()[0]['mode']=='auto'
    assert client.post('/zones/1/manual',json={'action':'start','duration_seconds':3}).status_code==200
    assert client.post('/zones/1/manual',json={'action':'stop'}).status_code==200
    assert client.get('/zones').json()[0]['mode']=='auto'


def test_missing_sensor_suspends_auto(client):
    client.post('/zones/1/sensors',json={'device_id':'esp32-1','sensor_id':'missing'})
    feed(client)
    client.put('/zones/1',json={'name':'z1','mode':'auto'})
    m.tick()
    assert not m.ACTIVE
    client.post('/zones/1/sensors',json={'device_id':'esp32-1','sensor_id':'s1'})
    # still missing second reading: fail closed
    m.tick()
    assert not m.ACTIVE


def test_growth_stage_and_safety(client):
    plants=client.get('/plants').json()
    pid=plants[0]['id']
    client.put(f'/plants/{pid}/stages',json={'stage':'germination','low':40,'high':60})
    client.put('/zones/1',json={'name':'Seedlings','mode':'auto','plant_id':pid,'growth_stage':'germination'})
    feed(client,value=30)
    m.tick()
    assert 1 in m.ACTIVE
    feed(client,value=70)
    m.tick()
    assert 1 not in m.ACTIVE
    assert client.get('/status').json()['zones'][0]['effective_thresholds']==[40,60]


def test_low_level_and_reports(client):
    r=client.post('/water-levels',json={'device_id':'esp32-1','sensor_id':'tank1','level_pct':5})
    assert r.status_code==201
    assert client.post('/zones/1/manual',json={}).status_code==409
    assert client.get('/notifications').json()[0]['event_type']=='low_water_level'
    feed(client)
    assert 'sensor_readings' in client.get('/reports/summary?period=week').json()
    assert 'sensor_id' in client.get('/exports/sensor_readings?period=month').text
    assert 'estimated_liters' in client.get('/exports/water_consumption').text


def test_limits_and_utc(client):
    client.put('/zones/1',json={'name':'z1','mode':'manual','duration_seconds':15,'max_duration_seconds':20,'daily_limit_liters':0.1,'flow_rate_lpm':3})
    x=client.post('/zones/1/manual',json={'duration_seconds':20}).json()
    assert x['ends_at']-x['started_at'] <= 2.01
    m.tick(x['ends_at']+1)
    assert not m.ACTIVE
    assert client.get('/dashboard').json()['estimated_total_liters_completed_sessions']>0


def test_legacy_migration(tmp_path,monkeypatch):
    import sqlite3
    path=str(tmp_path/'old.db')
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE zones(id INTEGER PRIMARY KEY,name TEXT NOT NULL,mode TEXT NOT NULL,low REAL NOT NULL,high REAL NOT NULL)')
        db.execute("INSERT INTO zones VALUES(1,'Original','manual',20,40)")
    monkeypatch.setattr(m,'DB',path)
    m.init();m.init()
    assert m.zone(1)['name']=='Original'
