"""Back up the app DB and replace the rejected V2 test replay with validated V3."""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TARGET = ROOT / 'runtime/smartfresh_v4.sqlite3'
SOURCE = ROOT / 'runtime/test_period_joint_2022_07_08_v3full2.sqlite3'
REPORT = ROOT / 'docs/JOINT_TWO_MONTH_JOINT_V3FULL2.json'
EVALUATION = ROOT / 'docs/JOINT_TWO_MONTH_V3_EVALUATION.json'


def promote():
    evaluation=json.loads(EVALUATION.read_text(encoding='utf-8'))
    if not evaluation.get('passed') or not all(evaluation.get('gates',{}).values()):
        raise ValueError('V3 must beat the ×10 baseline on waste, revenue and contribution in both months.')
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    expected = [row['session_id'] for row in report['rows']] + [report['next_session_id']]
    if len(report['rows']) != 62 or len(expected) != len(set(expected)):
        raise ValueError('The 62-day run and September session must be complete and unique.')
    source = sqlite3.connect(SOURCE)
    source.row_factory = sqlite3.Row
    states = [dict(row) for row in source.execute('SELECT id,state,updated FROM sessions ORDER BY rowid')]
    if [row['id'] for row in states] != expected:
        raise ValueError('Source sessions do not match the validated day sequence.')
    for index, row in enumerate(states):
        state = json.loads(row['state'])
        day = report['rows'][index]['day'] if index < 62 else '2022-09-01'
        phase = 'closed' if index < 62 else 'plan_pending'
        if state['day'] != day or state['phase'] != phase:
            raise ValueError('Source session day or phase is inconsistent.')
        if state.get('simulator_version')!='AEON_GENERATED_POS_V3':
            raise ValueError('Source session is not the V3 market.')
    next_state=json.loads(states[-1]['state'])
    next_state['auto_run']=True
    states[-1]['state']=json.dumps(next_state,ensure_ascii=False,allow_nan=False)
    # The HTTP close endpoint collects these labels. Reproduce that step for the
    # offline run, keeping generated POS rows separate from real training data.
    from services.engine import Engine
    from services.learning import Learning
    from services.store import Store
    collector = Learning(Store(SOURCE), Engine())
    for row in states[:-1]:
        collector.collect_simulation(json.loads(row['state']))
    target = sqlite3.connect(TARGET, timeout=30)
    target.row_factory = sqlite3.Row
    placeholders=','.join('?' for _ in expected)
    present=target.execute('SELECT state FROM sessions WHERE id IN ('+placeholders+')',expected).fetchall()
    for row in present:
        old=json.loads(row['state'])
        if old.get('simulator_version')!='AEON_GENERATED_POS_V2':
            raise ValueError('A conflicting session is not the rejected V2 test replay.')
        if old['day']=='2022-09-01' and old.get('revision',0)>0:
            raise ValueError('September V2 session was edited by a user; preserve it before replacement.')
    backup_dir = ROOT / 'runtime/backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup_path = backup_dir / f'smartfresh_v4_before_v3_replay_{stamp}.sqlite3'
    backup = sqlite3.connect(backup_path)
    target.backup(backup)
    backup.close()
    try:
        target.execute('BEGIN IMMEDIATE')
        for table,column in [('audit','session_id'),('safety_controls','sid'),
                             ('simulation_clocks','sid'),('reconciliation_receipts','session_id'),
                             ('monitoring_evaluations','sid'),('monitoring_jobs','sid')]:
            target.execute(f'DELETE FROM {table} WHERE {column} IN ({placeholders})',expected)
        target.execute("DELETE FROM learning_rows WHERE origin='simulation_x10' AND "
                       "substr(row_key,1,instr(row_key,':')-1) IN ("+placeholders+")",expected)
        target.execute('DELETE FROM sessions WHERE id IN ('+placeholders+')',expected)
        target.executemany('INSERT INTO sessions(id,state,updated) VALUES (?,?,?)',
                           [(row['id'],row['state'],row['updated']) for row in states])
        target.executemany('INSERT INTO audit(session_id,action,detail,created) VALUES (?,?,?,?)',
                           [(row['session_id'],row['action'],row['detail'],row['created'])
                            for row in source.execute('SELECT session_id,action,detail,created FROM audit ORDER BY id')])
        target.executemany('INSERT INTO safety_controls(sid,mode,faults,version) VALUES (?,?,?,?)',
                           [(row['sid'],row['mode'],row['faults'],row['version'])
                            for row in source.execute('SELECT sid,mode,faults,version FROM safety_controls')])
        target.executemany('INSERT INTO learning_rows(kind,origin,row_key,payload) VALUES (?,?,?,?)',
                           [(row['kind'],row['origin'],row['row_key'],row['payload'])
                            for row in source.execute('SELECT kind,origin,row_key,payload FROM learning_rows')])
        target.execute('INSERT INTO audit(session_id,action,detail) VALUES (?,?,?)',
                       (expected[-1],'TEST_PERIOD_IMPORTED',json.dumps({
                           'period':report['period'],'closed_days':62,'backup':str(backup_path),
                           'origin':'offline_generated_pos_v3_replay','replaced_v2_sessions':len(present)},ensure_ascii=False)))
        target.commit()
    except BaseException:
        target.rollback()
        raise
    finally:
        target.close()
        source.close()
    print(json.dumps({'imported_closed_days':62,'replaced_v2_sessions':len(present),'next_day':'2022-09-01',
                      'next_session_id':expected[-1],'backup':str(backup_path)},ensure_ascii=False))


if __name__ == '__main__':
    promote()
