"""Elapsed-window custodian for the x10 synthetic market, isolated from models."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.volume_scenario import SCALE, LEGACY_VOLUME_VERSION as VERSION, arrival_second, uniform


def process(request, source):
    operation, day = request['operation'], request['day']
    if operation not in ('consume', 'closed_evaluation'):
        raise ValueError('Invalid custodian operation')
    start, end = request.get('start', 480), request.get('end', 1320)
    prices = request.get('discounts', {})
    if type(start) is not int or type(end) is not int or not 480 <= start < end <= 1320:
        raise ValueError('Invalid elapsed window')
    if any(type(v) not in (int, float) or not 0 <= v <= 50 for v in prices.values()):
        raise ValueError('Invalid approved price')
    events, counts = [], {}
    with Path(source).open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['date'] != day:
                continue
            sku = row['sku_code']
            if operation == 'closed_evaluation':
                counts[sku] = counts.get(sku, 0) + SCALE * int(row['base_intent_qty'])
                continue
            for event in row['unit_events']:
                promo = bool(event['promo'])
                for replica in range(SCALE):
                    customer = f"{event['customer_id']}|x10:{replica}"
                    event_id = f"{event['event_id']}|x10:{replica}"
                    second = arrival_second(day, event['customer_id'], replica, request.get('seed', 42), request.get('holiday', False), promo,version=VERSION)
                    minute = second // 60
                    if not start <= minute < end:
                        continue
                    if promo:
                        probability = min(1., .6 * float(row.get('response_multiplier_assumed', 1)) * (prices.get(sku, 0) / 50) ** .9)
                        if uniform(f"{event_id}|{request.get('seed', 42)}|response") >= probability:
                            continue
                    events.append(dict(sku=sku, minute=minute, second=second, event_id=event_id,
                        customer_id=customer, quantity=1, origin=VERSION,
                        transaction_at=day + f'T{minute//60:02}:{minute%60:02}:{second%60:02}+07:00'))
    return {'counts': counts} if operation == 'closed_evaluation' else {'requests': sorted(events, key=lambda e: (e['second'], e['event_id']))}


if __name__ == '__main__':
    try:
        print(json.dumps(process(json.load(sys.stdin), sys.argv[1]), allow_nan=False))
    except Exception as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(1)
