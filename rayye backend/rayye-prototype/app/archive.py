"""Generate persistent monthly CSV archives from the Rayye SQLite history.
Usage: python -m app.archive --month 2026-11 --out archives
"""
import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from . import main as m

TABLES={
    'sensor_readings':('readings','received_at'),
    'watering_events':('watering_sessions','started_at'),
    'water_consumption':('watering_sessions','started_at'),
    'faults':('notifications','created_at'),
}

def archive_month(month, root):
    try:
        dt=datetime.strptime(month,'%Y-%m')
    except ValueError as e:
        raise ValueError('Month must be YYYY-MM') from e
    start=dt.replace(tzinfo=m.TZ)
    end=start.replace(year=start.year+1,month=1) if start.month==12 else start.replace(month=start.month+1)
    a=start.astimezone(timezone.utc).timestamp()
    b=end.astimezone(timezone.utc).timestamp()
    folder=Path(root)/start.strftime('%Y')/start.strftime('%m')
    folder.mkdir(parents=True,exist_ok=True)
    with m.conn() as db:
        for filename,(table,col) in TABLES.items():
            rows=[dict(r) for r in db.execute(f'SELECT * FROM {table} WHERE {col}>=? AND {col}<? ORDER BY {col}',(a,b))]
            if filename=='faults': rows=[r for r in rows if r['severity']!='info']
            if filename=='water_consumption': rows=[{'zone_id':r['zone_id'],'estimated_liters':r['estimated_liters'],'measurement':'estimated','started_at_utc':datetime.fromtimestamp(r['started_at'],timezone.utc).isoformat()} for r in rows]
            columns=list(rows[0]) if rows else {
                'sensor_readings':['id','zone_id','node_id','sensor_id','moisture','temperature','humidity','battery','received_at'],
                'watering_events':['id','zone_id','source','started_at','ended_at','stop_reason','estimated_liters'],
                'water_consumption':['zone_id','estimated_liters','measurement','started_at_utc'],
                'faults':['id','event_type','severity','zone_id','message','created_at','read_at','push_status'],
            }[filename]
            with (folder/(filename+'.csv')).open('w',newline='',encoding='utf-8') as out:
                w=csv.DictWriter(out,fieldnames=columns);w.writeheader();w.writerows(rows)
    return folder

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--month',required=True)
    parser.add_argument('--out',default='archives')
    args=parser.parse_args()
    m.init()
    print(archive_month(args.month,args.out))
