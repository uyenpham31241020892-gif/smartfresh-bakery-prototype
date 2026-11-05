import json

from services.store import Store


def test_closed_recent_uses_last_distinct_comparable_days(tmp_path):
    store=Store(tmp_path/'sessions.sqlite3')
    rows=[
        ('a', '2022-07-01',42,'hash',0),
        ('b', '2022-07-02',42,'hash',1),
        ('c', '2022-07-03',42,'hash',1),
        ('d', '2022-07-03',42,'hash',1),  # newer rerun of the same day
        ('e', '2022-07-04',43,'hash',0),
        ('f', '2022-07-04',42,'other',0),
        ('g', '2022-07-05',42,'hash',0),
        ('h', '2022-07-06',42,'hash',0),
    ]
    with store.connect() as db:
        for sid,day,seed,scenario,weekend in rows:
            state=dict(id=sid,day=day,seed=seed,phase='closed',mode='simulation',
                       model_version='joint',simulator_hash=scenario,
                       weather=dict(is_weekend=weekend,is_public_holiday=0))
            db.execute('INSERT INTO sessions(id,state) VALUES (?,?)',(sid,json.dumps(state)))
    selected=store.closed_recent('2022-07-06','simulation',42,'joint','hash',limit=3)
    assert [state['id'] for state in selected]==['g','d','b']
    weekends=store.closed_recent('2022-07-06','simulation',42,'joint','hash',
                                  limit=7,weekend_group=True)
    assert [state['id'] for state in weekends]==['d','b']
