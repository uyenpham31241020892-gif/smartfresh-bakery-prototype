"""Unproven discounts cannot pass the economic guard or revive old approvals."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.price_benefit import guard
from services.v606 import Engine,Simulator,BENEFIT_GUARD_VERSION
from services.workflow import Workflow
from services.store import Store
from services.safety import GuardError


class Benefit(unittest.TestCase):
    def test_break_even_uses_sunk_preparation_cost_and_holds_without_evidence(self):
        r=guard(dict(price=100,previous=0,new_price=80,discount=20,stock=100,prepared=140,sales30=10,sales60=20,minute=1170,reason='MARKDOWN'))
        self.assertEqual(r['new_price'],100);self.assertEqual(r['discount'],0)
        self.assertEqual(r['economic_gate']['discount_cost_on_same_units'],1000)
        self.assertEqual(r['economic_gate']['minimum_extra_units_to_break_even'],13)
        self.assertIsNone(r['economic_gate']['verified_net_benefit'])

    def test_existing_approved_price_is_not_raised(self):
        r=guard(dict(price=100,previous=10,new_price=80,discount=20,stock=30,sales30=1,sales60=2,minute=1260,reason='MARKDOWN'))
        self.assertEqual(r['new_price'],90);self.assertEqual(r['discount'],10)

    def test_pending_old_discount_is_superseded_without_changing_receipts_or_inventory(self):
        with tempfile.TemporaryDirectory() as t:
            e=Engine(version=BENEFIT_GUARD_VERSION);w=Workflow(e,Simulator(e),Store(Path(t)/'benefit.sqlite3'));s=w.create()
            for a in ('plan_approve','prepared'):s=w.mutate(s['id'],s['revision'],a)
            original=e.price
            def old_quote(*args,**kwargs):
                r=original(*args,**kwargs)
                return {**r,'discount':20,'new_price':round(r['price']*.8)}
            with patch.object(e,'price',side_effect=old_quote):s=w.mutate(s['id'],s['revision'],'tick',{'target':1170})
            self.assertEqual(s['phase'],'price_pending')
            with self.assertRaises(GuardError):w.mutate(s['id'],s['revision'],'price_approve',{'proposal_id':s['pending']['id']})
            ledger=s['ledger'];products=s['products']
            s=w.mutate(s['id'],s['revision'],'review_price_benefit',{'reason':'New benefit requirement'})
            self.assertEqual(s['phase'],'running');self.assertIsNone(s['pending'])
            self.assertEqual(s['ledger'],ledger);self.assertEqual(s['products'],products)
            self.assertTrue(any(d['status']=='superseded_economic_review' for d in s['decisions']))


if __name__=='__main__':unittest.main(verbosity=2)
