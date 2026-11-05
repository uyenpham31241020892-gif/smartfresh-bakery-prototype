import sys,copy,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.workflow import Workflow
class CheckpointReview(unittest.TestCase):
 def setup_case(self,minute,changed=False,origin='AI_M1',status='pending'):
  w=Workflow.__new__(Workflow)
  s=dict(minute=minute,phase='running',mode='simulation',pending=None,decisions=[],products={str(i):dict(stock=10,discount=20) for i in range(7)})
  w.proposals=lambda s:dict(minute=s['minute'],status=status,origin=origin,rows=[dict(sku=k,discount=30 if changed and k=='0' else 20) for k in s['products']])
  w.consume=lambda s,d:None
  return w,s
 def test_unchanged_prices_continue_at_every_checkpoint(self):
  for minute in (1170,1230,1290):
   w,s=self.setup_case(minute);w.pricing_checkpoint(s);self.assertEqual(s['phase'],'running');self.assertIsNone(s['pending']);self.assertEqual(len(s['decisions'][-1]['rows']),7)
 def test_optional_hold_logged_not_approved(self):
  for minute in (1200,1260):
   w,s=self.setup_case(minute);w.pricing_checkpoint(s);self.assertEqual(s['phase'],'running');self.assertIsNone(s['pending']);self.assertEqual(s['decisions'][-1]['status'],'auto_hold');self.assertIsNone(s['decisions'][-1]['approved_at']);self.assertEqual(s['products']['0']['discount'],20)
 def test_optional_change_stops(self):
  for minute in (1200,1260):
   w,s=self.setup_case(minute,True);w.pricing_checkpoint(s);self.assertEqual(s['phase'],'price_pending')
 def test_manual_or_missing_stops(self):
  for kwargs in [dict(origin='MANUAL_RULE'),dict(status='missing_data')]:
   w,s=self.setup_case(1200,**kwargs);w.pricing_checkpoint(s);self.assertEqual(s['phase'],'price_pending')
 def test_both_clock_routes_continue_to_next_mandatory(self):
  for action in ('do_tick','do_advance'):
   for start,target,stop in [(1170,1320,1320),(1230,1320,1320),(1290,1320,1320)]:
    w,s=self.setup_case(start);getattr(w,action)(s,{'target':target});self.assertEqual(s['minute'],stop);self.assertEqual(s['phase'],'close_pending' if stop==1320 else 'price_pending')
if __name__=='__main__':unittest.main()
