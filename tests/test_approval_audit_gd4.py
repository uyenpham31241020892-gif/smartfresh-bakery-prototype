"""GD4 regression tests: approve/reject/edit/stale/idempotency/audit."""
import copy
import pytest


def apply(flow, state, action, payload=None, key=None):
    return flow.mutate(state['id'], state['revision'], action, payload, key)


def test_plan_rejection_is_audited_and_blocks_preparation(flow):
    s = flow.create(day='2022-08-16', seed=42)
    initial_count = len(flow.store.audit(s['id']))
    with pytest.raises(ValueError):
        apply(flow, s, 'plan_reject', {'reason': ''})
    assert len(flow.store.audit(s['id'])) == initial_count
    rejected = apply(flow, s, 'plan_reject', {'reason': 'Test rejection'})
    assert rejected['phase'] == 'plan_rejected'
    assert flow.store.audit(s['id'])[0]['action'] == 'PLAN_REJECT'
    with pytest.raises(ValueError):
        apply(flow, rejected, 'prepared')


def test_plan_override_requires_reason_and_is_logged(flow):
    s = flow.create(day='2022-08-16', seed=42)
    row = s['plan'][0]
    qty = row['prepared'] + 4
    count = len(flow.store.audit(s['id']))
    with pytest.raises(ValueError, match='lý do'):
        apply(flow, s, 'plan_approve', {'quantities': {row['sku']: qty}})
    assert len(flow.store.audit(s['id'])) == count
    approved = apply(flow, s, 'plan_approve', {'quantities': {row['sku']: qty}, 'reason': 'Manual adjustment demo'})
    assert next(p for p in approved['plan'] if p['sku'] == row['sku'])['approved'] == qty
    assert flow.store.audit(s['id'])[0]['action'] == 'PLAN_APPROVE'
    assert flow.store.audit(s['id'])[0]['detail'].find('Manual adjustment demo') >= 0


def test_revisions_and_failed_actions_do_not_write_audit(flow):
    s = flow.create(day='2022-08-16', seed=42)
    a = apply(flow, s, 'plan_approve')
    n = len(flow.store.audit(s['id']))
    with pytest.raises(ValueError, match='thay đổi'):
        flow.mutate(s['id'], s['revision'], 'prepared')
    assert flow.store.get(s['id']) == a
    assert len(flow.store.audit(s['id'])) == n


def test_price_approval_not_application_duplicate_apply_no_extra_audit(flow):
    s = flow.create(day='2022-08-16', seed=42)
    s = apply(flow, s, 'plan_approve')
    s = apply(flow, s, 'prepared')
    s = apply(flow, s, 'advance', {'target': 1170})
    pid = s['pending']['id']
    original = {sku: p['discount'] for sku,p in s['products'].items()}
    approved = apply(flow, s, 'price_approve', {'proposal_id': pid})
    assert {sku: p['discount'] for sku,p in approved['products'].items()} == original
    applied = apply(flow, approved, 'price_apply', {'proposal_id': pid}, key='gd4-'+pid)
    n = len(flow.store.audit(s['id']))
    duplicate = flow.mutate(s['id'], approved['revision'], 'price_apply', {'proposal_id': pid}, key='gd4-'+pid)
    assert duplicate == applied
    assert len(flow.store.audit(s['id'])) == n
    assert [x['action'] for x in flow.store.audit(s['id'])[:2]] == ['PRICE_APPLY', 'PRICE_APPROVE']
