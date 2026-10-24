"""Cached explanation jobs read the captured proposal, not a later live state."""
import sys
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.explanations import Explanations

class ExplanationTests(unittest.TestCase):
 def test_single_job_immutable_snapshot_and_evidence(self):
  service=Explanations();release=Event();calls=[]
  state=dict(id='test',model_version='V606',input_hash='frozen-plan',pending=None,decisions=[],minute=360)
  def chat(question,s,evidence):
   release.wait(3);calls.append((s['minute'],evidence('TP-DN-001')))
   return dict(answer='Explanation',provider='test',model='mock',tools_used=['get_session_context','get_model_evidence'])
  client=SimpleNamespace(provider='test',model='mock',key='',chat=chat)
  try:
   a=service.get(state,'m2',client,lambda s,sku:{'as_of':s['minute'],'sku':sku})
   self.assertEqual(a['status'],'running');state['minute']=1170
   service.get(state,'m2',client,lambda s,sku:{'as_of':s['minute'],'sku':sku})
   release.set();service.pool.shutdown(wait=True)
   result=service.get(state,'m2',client,lambda s,sku:None)
   self.assertEqual(result['status'],'ready');self.assertEqual(result['as_of_minute'],360)
   self.assertEqual(calls,[(360,{'as_of':360,'sku':'TP-DN-001'})])
  finally:release.set();service.pool.shutdown(wait=True)

if __name__=='__main__':unittest.main(verbosity=2)
