"""Rayye v0.3: database-backed SIMULATION. Never drives GPIO or serial outputs."""
import asyncio
import csv
import io
import json
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, ConfigDict, model_validator

DB = os.getenv('RAYYE_DB', 'rayye.db')
TOKEN = os.getenv('RAYYE_API_TOKEN', '')
LOCK = RLock()
AUTH = HTTPBearer(auto_error=False)
TZ = ZoneInfo('Africa/Cairo')
FRESH_NORMAL = 16 * 60  # a missed 15 minute report gets a small grace period
FRESH_ACTIVE = 20       # 5-10 second reporting during irrigation
ACTIVE = {}             # zone ID -> bounded simulated watering session
SUBSCRIBERS = set()


def auth(credentials: HTTPAuthorizationCredentials | None = Depends(AUTH)):
    if not TOKEN or credentials is None or not secrets.compare_digest(credentials.credentials, TOKEN):
        raise HTTPException(401, 'Bearer RAYYE_API_TOKEN required')


def conn():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    return db


def columns(db, table):
    return {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}


def init():
    with conn() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS zones(id INTEGER PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'manual', low REAL NOT NULL DEFAULT 30, high REAL NOT NULL DEFAULT 55, stop_rule TEXT NOT NULL DEFAULT 'both', duration_seconds INTEGER NOT NULL DEFAULT 60, preset_id INTEGER);
        CREATE TABLE IF NOT EXISTS readings(id INTEGER PRIMARY KEY, zone_id INTEGER, node_id TEXT, sensor_id TEXT, moisture REAL, temperature REAL, humidity REAL, battery REAL, received_at REAL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, zone_id INTEGER, action TEXT, reason TEXT, at REAL);
        CREATE TABLE IF NOT EXISTS plants(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, notes TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS soils(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, notes TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, kind TEXT NOT NULL, transport TEXT NOT NULL, last_seen REAL, enabled INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS water_levels(id INTEGER PRIMARY KEY, device_id TEXT, sensor_id TEXT, level_pct REAL, received_at REAL);
        CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, event_type TEXT NOT NULL, severity TEXT NOT NULL, zone_id INTEGER, message TEXT NOT NULL, created_at REAL NOT NULL, read_at REAL, push_status TEXT NOT NULL DEFAULT 'pending');
        CREATE TABLE IF NOT EXISTS plant_stages(id INTEGER PRIMARY KEY, plant_id INTEGER NOT NULL REFERENCES plants(id), stage TEXT NOT NULL, low REAL NOT NULL, high REAL NOT NULL, UNIQUE(plant_id,stage));
        CREATE TABLE IF NOT EXISTS watering_sessions(id INTEGER PRIMARY KEY, zone_id INTEGER NOT NULL, source TEXT NOT NULL, started_at REAL NOT NULL, ended_at REAL, stop_reason TEXT, estimated_liters REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS configuration(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS zone_sensors(zone_id INTEGER NOT NULL, device_id TEXT NOT NULL, sensor_id TEXT NOT NULL, PRIMARY KEY(zone_id,device_id,sensor_id));
        CREATE INDEX IF NOT EXISTS idx_readings ON readings(zone_id,received_at);
        CREATE INDEX IF NOT EXISTS idx_events ON events(at);
        ''')
        # Additive migrations support the previous prototype's SQLite database.
        migrations = {'zones': {'stop_rule': "TEXT DEFAULT 'both'", 'duration_seconds':'INTEGER DEFAULT 60', 'preset_id':'INTEGER', 'max_duration_seconds':'INTEGER DEFAULT 180', 'cooldown_seconds':'INTEGER DEFAULT 300', 'daily_limit_liters':'REAL DEFAULT 50', 'flow_rate_lpm':'REAL DEFAULT 2', 'plant_id':'INTEGER', 'soil_id':'INTEGER', 'growth_stage':"TEXT DEFAULT 'vegetative'", 'area_m2':'REAL DEFAULT 1'}, 'readings': {}, 'events': {}}
        for table, fields in migrations.items():
            available = columns(db, table)
            for key, spec in fields.items():
                if key not in available:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN {key} {spec}')
        for key, val in {'pump_capacity_zones':'2', 'location':'Port Said, Egypt', 'area_m2':'2', 'low_water_level_pct':'15', 'active_sampling_seconds':'10', 'normal_sampling_seconds':'900'}.items():
            db.execute('INSERT OR IGNORE INTO configuration(key,value) VALUES(?,?)', (key,json.dumps(val)))
        if not db.execute('SELECT 1 FROM zones LIMIT 1').fetchone():
            db.executemany('INSERT INTO zones(id,name,mode,low,high,stop_rule,duration_seconds) VALUES(?,?,?,?,?,?,?)',[(1,'Zone 1','manual',30,55,'both',60),(2,'Zone 2','manual',30,55,'both',60)])
        for d in [('mega-1','arduino-mega','usb-serial'),('esp32-1','esp32','wifi'),('esp32-2','esp32','wifi')]:
            db.execute('INSERT OR IGNORE INTO devices(id,kind,transport) VALUES(?,?,?)',d)
        for name in ['Basil','Mint','Tomato','Lettuce']:
            db.execute('INSERT OR IGNORE INTO plants(name,notes) VALUES(?,?)',(name,'Starter entry; calibrate thresholds for actual plant and substrate'))
        for name in ['Sandy','Loamy','Clay','Coco coir']:
            db.execute('INSERT OR IGNORE INTO soils(name,notes) VALUES(?,?)',(name,'Starter entry; no universal sensor calibration implied'))
        # No fabricated thresholds for growth stages: user must enter validated values.


def record_event(zone, action, reason, at=None):
    at = time.time() if at is None else at
    with conn() as db:
        db.execute('INSERT INTO events(zone_id,action,reason,at) VALUES(?,?,?,?)',(zone,action,reason,at))


EVENT_SEVERITY = {'sensor_disconnected':'high','device_disconnected':'critical','low_water_level':'high','actuator_failure':'critical','excessive_moisture':'high','emergency_shutdown':'critical','watering_completed':'info','daily_limit_reached':'warning'}

def notify(kind, zone, message):
    if kind not in EVENT_SEVERITY:
        raise ValueError('Unknown notification type')
    with conn() as db:
        db.execute('INSERT INTO notifications(event_type,severity,zone_id,message,created_at) VALUES(?,?,?,?,?)',(kind,EVENT_SEVERITY[kind],zone,message,time.time()))
    # Push notifications are queued, not claimed delivered without an FCM implementation.


def setting(key):
    with conn() as db:
        r=db.execute('SELECT value FROM configuration WHERE key=?',(key,)).fetchone()
    return json.loads(r['value']) if r else None


def zone(zid):
    with conn() as db:
        r=db.execute('SELECT * FROM zones WHERE id=?',(zid,)).fetchone()
    if r is None: raise HTTPException(404,'Zone not found')
    return dict(r)


def readings_for_zone(zid, now):
    with conn() as db:
        mapped=db.execute('SELECT device_id,sensor_id FROM zone_sensors WHERE zone_id=?',(zid,)).fetchall()
        if not mapped:
            mapped=db.execute('SELECT DISTINCT node_id device_id,sensor_id FROM readings WHERE zone_id=?',(zid,)).fetchall()
        result=[]
        for sensor in mapped:
            r=db.execute('SELECT * FROM readings WHERE zone_id=? AND node_id=? AND sensor_id=? ORDER BY id DESC LIMIT 1',(zid,sensor['device_id'],sensor['sensor_id'])).fetchone()
            result.append(dict(r) if r else None)
    return result


def moisture(zid, now, active=False):
    rows=readings_for_zone(zid,now)
    freshness=FRESH_ACTIVE if active else FRESH_NORMAL
    if not rows or any(r is None or now-r['received_at']>freshness for r in rows):
        return None
    return sum(r['moisture'] for r in rows)/len(rows)


def thresholds(z):
    if z['plant_id']:
        with conn() as db:
            r=db.execute('SELECT low,high FROM plant_stages WHERE plant_id=? AND stage=?',(z['plant_id'],z['growth_stage'])).fetchone()
        if r: return r['low'],r['high']
        return None  # fail safe until configured
    return z['low'],z['high']


def daily_usage(zid, now):
    start=datetime.fromtimestamp(now,TZ).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc).timestamp()
    with conn() as db:
        r=db.execute('SELECT COALESCE(SUM(estimated_liters),0) n FROM watering_sessions WHERE zone_id=? AND started_at>=?',(zid,start)).fetchone()
    amount=r['n']
    if zid in ACTIVE:
        s=ACTIVE[zid]
        amount+=(max(0,now-s['started_at'])/60)*s['flow_rate_lpm']
    return amount


def stop_one(zid, reason, now=None):
    now = time.time() if now is None else now
    session=ACTIVE.pop(zid,None)
    if not session: return False
    liters=max(0,now-session['started_at'])/60*session['flow_rate_lpm']
    with conn() as db:
        db.execute('UPDATE watering_sessions SET ended_at=?,stop_reason=?,estimated_liters=? WHERE id=?',(now,reason,liters,session['session_id']))
    record_event(zid,'stop',reason,now)
    notify('watering_completed',zid,f'Watering stopped: {reason}')
    if session['source']=='manual':
        # Previous automatic mode remains in the database, and resumes on next tick.
        pass
    return True


def start_one(zid, source, requested=None, now=None):
    now=time.time() if now is None else now
    z=zone(zid)
    if zid in ACTIVE: return ACTIVE[zid]
    if len(ACTIVE)>=int(setting('pump_capacity_zones')): raise HTTPException(409,'Configured pump capacity reached')
    if daily_usage(zid,now)>=z['daily_limit_liters']:
        notify('daily_limit_reached',zid,'Daily watering allowance reached')
        raise HTTPException(409,'Daily limit reached')
    with conn() as db:
        low=db.execute('SELECT level_pct FROM water_levels ORDER BY id DESC LIMIT 1').fetchone()
    if low is not None and low['level_pct'] < float(setting('low_water_level_pct')):
        raise HTTPException(409,'Low water level: watering blocked')
    duration=min(requested or z['duration_seconds'],z['max_duration_seconds'])
    allowed=(z['daily_limit_liters']-daily_usage(zid,now))/z['flow_rate_lpm']*60
    duration=min(duration,allowed)
    if duration<=0: raise HTTPException(409,'Daily limit reached')
    with conn() as db:
        cur=db.execute('INSERT INTO watering_sessions(zone_id,source,started_at) VALUES(?,?,?)',(zid,source,now))
        sid=cur.lastrowid
    ACTIVE[zid]={'zone_id':zid,'source':source,'started_at':now,'ends_at':now+duration,'session_id':sid,'flow_rate_lpm':z['flow_rate_lpm']}
    record_event(zid,'start',source,now)
    return dict(ACTIVE[zid])


def tick(now=None):
    now=time.time() if now is None else now
    with LOCK:
        for zid,s in list(ACTIVE.items()):
            z=zone(zid)
            if now>=s['ends_at']:
                stop_one(zid,'maximum duration / daily allowance',now)
            elif s['source']=='auto':
                m=moisture(zid,now,True)
                bands=thresholds(z)
                if m is None or bands is None:
                    stop_one(zid,'sensor missing or stale',now)
                    notify('sensor_disconnected',zid,'Automatic watering suspended: sensor data missing or stale')
                elif m>=bands[1]: stop_one(zid,'upper moisture threshold',now)
        # Device health alarms: suppress repeat alerts for an hour.
        with conn() as db:
            devices=[dict(x) for x in db.execute('SELECT * FROM devices WHERE last_seen IS NOT NULL')]
        for device in devices:
            if now-device['last_seen'] > FRESH_NORMAL:
                label=f"Device {device['id']} communication timeout"
                with conn() as db:
                    recent=db.execute('SELECT 1 FROM notifications WHERE event_type=? AND message=? AND created_at>?',('device_disconnected',label,now-3600)).fetchone()
                if not recent: notify('device_disconnected',None,label)
        with conn() as db:
            rows=db.execute("SELECT id FROM zones WHERE mode='auto' ORDER BY id").fetchall()
        for row in rows:
            zid=row['id']
            if zid in ACTIVE or len(ACTIVE)>=int(setting('pump_capacity_zones')): continue
            z=zone(zid)
            bands=thresholds(z)
            m=moisture(zid,now)
            if m is None or bands is None:
                with conn() as db:
                    mapped=db.execute('SELECT COUNT(*) n FROM zone_sensors WHERE zone_id=?',(zid,)).fetchone()['n']
                    previously=db.execute('SELECT COUNT(*) n FROM readings WHERE zone_id=?',(zid,)).fetchone()['n']
                    recent=db.execute('SELECT 1 FROM notifications WHERE event_type=? AND zone_id=? AND created_at>?',('sensor_disconnected',zid,now-3600)).fetchone()
                if (mapped or previously) and not recent:
                    notify('sensor_disconnected',zid,'Automatic mode suspended; assigned moisture readings unavailable or growth thresholds unconfigured')
                continue
            with conn() as db:
                last=db.execute("SELECT MAX(at) val FROM events WHERE zone_id=? AND action='stop'",(zid,)).fetchone()['val']
            if m<bands[0] and (last is None or now-last>=z['cooldown_seconds']):
                try: start_one(zid,'auto',now=now)
                except HTTPException: pass


async def background():
    while True:
        tick()
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app):
    init()
    record_event(None,'startup','outputs simulated OFF')
    t=asyncio.create_task(background())
    try: yield
    finally:
        t.cancel()
        try: await t
        except asyncio.CancelledError: pass
        with LOCK:
            for zid in list(ACTIVE): stop_one(zid,'server shutdown')


app=FastAPI(title='Rayye Irrigation API', version='0.3.0',lifespan=lifespan,description='Simulation-only API, bearer token required for REST operations. See /docs.')

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')

class Zone(Strict):
    name:str=Field(min_length=1,max_length=80)
    mode:Literal['auto','manual']='manual'
    low:float=Field(default=30,ge=0,le=100)
    high:float=Field(default=55,ge=0,le=100)
    duration_seconds:int=Field(default=60,ge=1,le=3600)
    max_duration_seconds:int=Field(default=180,ge=1,le=3600)
    cooldown_seconds:int=Field(default=300,ge=0,le=86400)
    daily_limit_liters:float=Field(default=50,gt=0,le=100000)
    flow_rate_lpm:float=Field(default=2,gt=0,le=10000)
    plant_id:int|None=None
    soil_id:int|None=None
    growth_stage:str=Field(default='vegetative',min_length=1,max_length=40)
    area_m2:float=Field(default=1,gt=0)
    @model_validator(mode='after')
    def check(self):
        if self.low>=self.high: raise ValueError('low must be less than high')
        if self.duration_seconds>self.max_duration_seconds: raise ValueError('duration cannot exceed maximum duration')
        return self

class Telemetry(Strict):
    zone_id:int
    node_id:str=Field(min_length=1,max_length=64)
    sensor_id:str=Field(min_length=1,max_length=64)
    moisture:float=Field(ge=0,le=100,allow_inf_nan=False)
    temperature:float|None=Field(default=None,ge=-40,le=100)
    humidity:float|None=Field(default=None,ge=0,le=100)
    battery:float|None=Field(default=None,ge=0,le=100)

class Level(Strict):
    device_id:str
    sensor_id:str
    level_pct:float=Field(ge=0,le=100)

class Device(Strict):
    id:str=Field(min_length=1,max_length=64)
    kind:Literal['arduino-mega','esp32']
    transport:Literal['usb-serial','wifi']

class Catalog(Strict):
    name:str=Field(min_length=1,max_length=80)
    notes:str=''

class Stage(Strict):
    stage:str=Field(min_length=1,max_length=40)
    low:float=Field(ge=0,le=100)
    high:float=Field(ge=0,le=100)
    @model_validator(mode='after')
    def check(self):
        if self.low>=self.high: raise ValueError('low must be less than high')
        return self

class Manual(Strict):
    action:Literal['start','stop']='start'
    duration_seconds:int|None=Field(default=None,ge=1,le=3600)

class Config(Strict):
    pump_capacity_zones:int=Field(ge=1,le=2)
    location:str=Field(min_length=1)
    area_m2:float=Field(gt=0)
    low_water_level_pct:float=Field(ge=0,le=100)

class SensorAssignment(Strict):
    device_id:str
    sensor_id:str

@app.get('/health')
def health(): return {'status':'ok','hardware':'simulated','version':'0.3.0'}

@app.get('/setup',dependencies=[Depends(auth)])
def setup():
    with conn() as db: return {r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM configuration')}

@app.put('/setup',dependencies=[Depends(auth)])
def setup_update(body:Config):
    with LOCK,conn() as db:
        for k,v in body.model_dump().items(): db.execute('INSERT OR REPLACE INTO configuration(key,value) VALUES(?,?)',(k,json.dumps(v)))
    return setup()

@app.get('/devices',dependencies=[Depends(auth)])
def devices():
    with conn() as db: return [dict(r) for r in db.execute('SELECT * FROM devices ORDER BY id')]

@app.post('/devices',dependencies=[Depends(auth)],status_code=201)
def device_create(body:Device):
    with conn() as db:
        try: db.execute('INSERT INTO devices(id,kind,transport) VALUES(?,?,?)',tuple(body.model_dump().values()))
        except sqlite3.IntegrityError: raise HTTPException(409,'Device exists')
    return body

@app.post('/devices/{device_id}/heartbeat',dependencies=[Depends(auth)])
def heartbeat(device_id:str):
    with conn() as db:
        cur=db.execute('UPDATE devices SET last_seen=? WHERE id=?',(time.time(),device_id))
        if not cur.rowcount: raise HTTPException(404,'Device missing')
    return {'device_id':device_id,'received':True}

@app.get('/zones',dependencies=[Depends(auth)])
def zones():
    with conn() as db: return [dict(r) for r in db.execute('SELECT * FROM zones ORDER BY id')]

@app.post('/zones',dependencies=[Depends(auth)],status_code=201)
def zone_create(body:Zone):
    with LOCK,conn() as db:
        data=body.model_dump()
        cols=','.join(data)
        q=','.join('?' for _ in data)
        cur=db.execute(f'INSERT INTO zones({cols}) VALUES({q})',tuple(data.values()))
        zid=cur.lastrowid
    return zone(zid)

@app.put('/zones/{zid}',dependencies=[Depends(auth)])
def zone_update(zid:int,body:Zone):
    with LOCK:
        zone(zid)
        if zid in ACTIVE: stop_one(zid,'configuration changed')
        data=body.model_dump()
        with conn() as db:
            db.execute('UPDATE zones SET '+','.join(f'{key}=?' for key in data)+' WHERE id=?',(*data.values(),zid))
    return zone(zid)

@app.delete('/zones/{zid}',dependencies=[Depends(auth)])
def zone_delete(zid:int):
    with LOCK:
        zone(zid)
        if zid in ACTIVE: raise HTTPException(409,'Stop watering first')
        with conn() as db:
            db.execute('DELETE FROM zone_sensors WHERE zone_id=?',(zid,))
            db.execute('DELETE FROM zones WHERE id=?',(zid,))
    return {'deleted':zid}

@app.post('/zones/{zid}/sensors',dependencies=[Depends(auth)])
def assign_sensor(zid:int,body:SensorAssignment):
    zone(zid)
    with conn() as db:
        if not db.execute('SELECT 1 FROM devices WHERE id=?',(body.device_id,)).fetchone(): raise HTTPException(404,'Device missing')
        db.execute('INSERT OR IGNORE INTO zone_sensors VALUES(?,?,?)',(zid,body.device_id,body.sensor_id))
    return {'zone_id':zid,**body.model_dump()}

@app.post('/telemetry',dependencies=[Depends(auth)],status_code=201)
def telemetry(body:Telemetry):
    zone(body.zone_id)
    now=time.time()
    with conn() as db:
        cur=db.execute('INSERT INTO readings(zone_id,node_id,sensor_id,moisture,temperature,humidity,battery,received_at) VALUES(?,?,?,?,?,?,?,?)',(*body.model_dump().values(),now))
        db.execute('UPDATE devices SET last_seen=? WHERE id=?',(now,body.node_id))
        row_id=cur.lastrowid
    z=zone(body.zone_id)
    bands=thresholds(z)
    if bands is not None and body.moisture>bands[1]:
        with conn() as db:
            recent=db.execute('SELECT 1 FROM notifications WHERE event_type=? AND zone_id=? AND created_at>?',('excessive_moisture',body.zone_id,now-3600)).fetchone()
        if not recent: notify('excessive_moisture',body.zone_id,'Moisture exceeds configured upper threshold')
    return {'id':row_id,'received_at':now}

@app.post('/water-levels',dependencies=[Depends(auth)],status_code=201)
def level(body:Level):
    now=time.time()
    with conn() as db:
        cur=db.execute('INSERT INTO water_levels(device_id,sensor_id,level_pct,received_at) VALUES(?,?,?,?)',(*body.model_dump().values(),now))
        row_id=cur.lastrowid
    if body.level_pct<float(setting('low_water_level_pct')):
        with LOCK:
            for zid in list(ACTIVE): stop_one(zid,'low water level',now)
            notify('low_water_level',None,f'Water level {body.level_pct}% on {body.sensor_id}')
    return {'id':row_id}

@app.get('/zones/{zid}/telemetry',dependencies=[Depends(auth)])
def history(zid:int,limit:int=100):
    zone(zid)
    if not 1<=limit<=1000: raise HTTPException(422,'Limit must be 1..1000')
    with conn() as db: return [dict(r) for r in db.execute('SELECT * FROM readings WHERE zone_id=? ORDER BY id DESC LIMIT ?',(zid,limit))]

@app.post('/zones/{zid}/manual',dependencies=[Depends(auth)])
def manual(zid:int,body:Manual):
    with LOCK:
        zone(zid)
        if body.action=='stop':
            stop_one(zid,'manual stop')
            return {'zone_id':zid,'watering':False,'mode':zone(zid)['mode']}
        return start_one(zid,'manual',body.duration_seconds)

@app.post('/zones/{zid}/water',dependencies=[Depends(auth)])
def water(zid:int,body:Manual):
    return manual(zid,Manual(action='start',duration_seconds=body.duration_seconds))

@app.post('/stop',dependencies=[Depends(auth)])
def emergency():
    with LOCK:
        with conn() as db:
            db.execute("UPDATE zones SET mode='manual'")
        for zid in list(ACTIVE): stop_one(zid,'emergency shutdown')
        notify('emergency_shutdown',None,'Emergency stop invoked, automatic mode disabled')
    return {'pump_on':False,'automatic_modes_disabled':True}

@app.get('/status',dependencies=[Depends(auth)])
def status():
    now=time.time()
    with LOCK:
        return {'hardware':'simulated','pump_on':bool(ACTIVE),'active':list(ACTIVE.values()),'zones':[dict(z,moisture=moisture(z['id'],now),effective_thresholds=thresholds(z),estimated_daily_liters=daily_usage(z['id'],now)) for z in zones()]}

@app.get('/events',dependencies=[Depends(auth)])
def events(limit:int=100):
    with conn() as db: return [dict(r) for r in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?',(min(1000,max(1,limit)),))]

@app.get('/notifications',dependencies=[Depends(auth)])
def notifications():
    with conn() as db: return [dict(r) for r in db.execute('SELECT * FROM notifications ORDER BY id DESC LIMIT 200')]

@app.post('/notifications/{nid}/read',dependencies=[Depends(auth)])
def mark_read(nid:int):
    with conn() as db:
        result=db.execute('UPDATE notifications SET read_at=? WHERE id=?',(time.time(),nid))
        if not result.rowcount: raise HTTPException(404,'Notification not found')
    return {'read':nid}

@app.get('/plants',dependencies=[Depends(auth)])
def plants(): return catalog_list('plants')
@app.get('/soils',dependencies=[Depends(auth)])
def soils(): return catalog_list('soils')

def catalog_list(table):
    with conn() as db: return [dict(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY id')]

def add_catalog(table,body):
    with conn() as db:
        try:
            cur=db.execute(f'INSERT INTO {table}(name,notes) VALUES(?,?)',(body.name,body.notes))
        except sqlite3.IntegrityError: raise HTTPException(409,'Duplicate name')
    return {'id':cur.lastrowid,**body.model_dump()}

@app.post('/plants',dependencies=[Depends(auth)],status_code=201)
def add_plant(body:Catalog): return add_catalog('plants',body)
@app.post('/soils',dependencies=[Depends(auth)],status_code=201)
def add_soil(body:Catalog): return add_catalog('soils',body)

@app.put('/plants/{pid}/stages',dependencies=[Depends(auth)])
def stage_upsert(pid:int,body:Stage):
    with conn() as db:
        if not db.execute('SELECT 1 FROM plants WHERE id=?',(pid,)).fetchone(): raise HTTPException(404,'Plant missing')
        db.execute('INSERT INTO plant_stages(plant_id,stage,low,high) VALUES(?,?,?,?) ON CONFLICT(plant_id,stage) DO UPDATE SET low=excluded.low,high=excluded.high',(pid,body.stage,body.low,body.high))
    return {'plant_id':pid,**body.model_dump()}

@app.get('/plants/{pid}/stages',dependencies=[Depends(auth)])
def stages(pid:int):
    with conn() as db: return [dict(r) for r in db.execute('SELECT * FROM plant_stages WHERE plant_id=?',(pid,))]

@app.get('/dashboard',dependencies=[Depends(auth)])
def dashboard():
    now=time.time()
    with conn() as db:
        counts={r['event_type']:r['n'] for r in db.execute('SELECT event_type,COUNT(*) n FROM notifications WHERE read_at IS NULL GROUP BY event_type')}
        water=db.execute('SELECT COALESCE(SUM(estimated_liters),0) total FROM watering_sessions').fetchone()['total']
        levels=[dict(r) for r in db.execute('SELECT w.* FROM water_levels w JOIN (SELECT device_id,sensor_id,MAX(id) id FROM water_levels GROUP BY device_id,sensor_id) x ON w.id=x.id')]
    return {'at_utc':datetime.fromtimestamp(now,timezone.utc).isoformat(),'active_zones':list(ACTIVE),'zones':status()['zones'],'unread_notifications':counts,'estimated_total_liters_completed_sessions':water,'water_levels':levels}

@app.get('/reports/summary',dependencies=[Depends(auth)])
def report_summary(period:Literal['day','week','month']='day',date:str|None=None):
    try: dt=datetime.strptime(date,'%Y-%m-%d').replace(tzinfo=TZ) if date else datetime.now(TZ)
    except ValueError: raise HTTPException(422,'date must be YYYY-MM-DD')
    if period=='day': start=dt.replace(hour=0,minute=0,second=0,microsecond=0); end=start+timedelta(days=1)
    elif period=='week': start=(dt-timedelta(days=(dt.weekday()+2)%7)).replace(hour=0,minute=0,second=0,microsecond=0);end=start+timedelta(days=7)
    else:
        start=dt.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        end=start.replace(year=start.year+1,month=1) if start.month==12 else start.replace(month=start.month+1)
    a,b=start.astimezone(timezone.utc).timestamp(),end.astimezone(timezone.utc).timestamp()
    with conn() as db:
        count=db.execute('SELECT COUNT(*) n FROM readings WHERE received_at>=? AND received_at<?',(a,b)).fetchone()['n']
        water=db.execute('SELECT COUNT(*) sessions,COALESCE(SUM(estimated_liters),0) liters FROM watering_sessions WHERE started_at>=? AND started_at<?',(a,b)).fetchone()
        faults=db.execute('SELECT COUNT(*) n FROM notifications WHERE created_at>=? AND created_at<? AND severity != ?', (a,b,'info')).fetchone()['n']
    return {'period':period,'start_local':start.isoformat(),'end_local':end.isoformat(),'sensor_readings':count,'watering_sessions':water['sessions'],'estimated_liters':water['liters'],'fault_notifications':faults,'consumption_method':'estimated from configured flow rate, not measured'}

REPORT_TABLES={'sensor_readings':('readings','received_at'),'watering_events':('watering_sessions','started_at'),'water_consumption':('watering_sessions','started_at'),'faults':('notifications','created_at')}
@app.get('/exports/{kind}',dependencies=[Depends(auth)])
def export_csv(kind:str,period:Literal['day','week','month']='month',date:str|None=None):
    if kind not in REPORT_TABLES: raise HTTPException(404,'Unknown report')
    span=report_summary(period,date)
    a=datetime.fromisoformat(span['start_local']).timestamp()
    b=datetime.fromisoformat(span['end_local']).timestamp()
    table,col=REPORT_TABLES[kind]
    with conn() as db:
        query=f'SELECT * FROM {table} WHERE {col}>=? AND {col}<?'
        if kind=='faults': query+=' AND severity != \'info\''
        rows=[dict(x) for x in db.execute(query+' ORDER BY '+col,(a,b))]
    if kind=='water_consumption':
        rows=[{'zone_id':r['zone_id'],'started_at_utc':datetime.fromtimestamp(r['started_at'],timezone.utc).isoformat(),'estimated_liters':r['estimated_liters'],'measurement':'estimated'} for r in rows]
    output=io.StringIO()
    fields=list(rows[0]) if rows else ({'sensor_readings':['id','zone_id','node_id','sensor_id','moisture','temperature','humidity','battery','received_at'],'watering_events':['id','zone_id','source','started_at','ended_at','stop_reason','estimated_liters'],'water_consumption':['zone_id','started_at_utc','estimated_liters','measurement'],'faults':['id','event_type','severity','zone_id','message','created_at','read_at','push_status']}[kind])
    writer=csv.DictWriter(output,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    filename=f'rayye_{kind}_{period}_{(date or datetime.now(TZ).strftime("%Y-%m-%d"))}.csv'
    return StreamingResponse(iter([output.getvalue()]),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{filename}"'})

@app.websocket('/ws/live')
async def live(websocket:WebSocket):
    # Client authenticates with first JSON message after secure WS connect.
    # Use wss:// over untrusted networks; no URL or subprotocol token exposure.
    await websocket.accept()
    try:
        supplied=await asyncio.wait_for(websocket.receive_json(), timeout=5)
        candidate=supplied.get('token') if isinstance(supplied,dict) else None
        if not TOKEN or not isinstance(candidate,str) or not secrets.compare_digest(candidate,TOKEN):
            await websocket.close(code=1008)
            return
        while True:
            await websocket.send_json({'type':'status','data':status()})
            await asyncio.sleep(10)
    except (WebSocketDisconnect,RuntimeError,asyncio.TimeoutError,ValueError):
        try: await websocket.close()
        except RuntimeError: pass
