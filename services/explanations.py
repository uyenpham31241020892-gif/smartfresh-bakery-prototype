"""Read-only, cached Copilot explanations tied to immutable proposal snapshots."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Lock
import hashlib
import json

class Explanations:
 def __init__(self):
  self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='proposal-explanation')
  self.report_pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='report-explanation')
  self.jobs={};self.contexts={};self.lock=Lock()
 def invalidate_errors(self):
  with self.lock:
   for key,(job,_) in list(self.jobs.items()):
    if job.done() and job.exception() is not None:del self.jobs[key]
 def get(self,state,component,assistant,evidence,report_context=None):
  if component not in ('m1','m2','reports'):raise ValueError('Unknown explanation component')
  proposal=state.get('pending') or (state['decisions'][-1] if state['decisions'] else {})
  stamp=state['input_hash'] if component=='m2' else proposal.get('id','before-checkpoint')
  if component=='reports':
   if report_context is None:raise ValueError('Missing report context')
   stamp=json.dumps([report_context['scope'],state['phase']=='closed'],sort_keys=True)
  identity=[state['id'],state['model_version'],component,stamp,assistant.provider,assistant.model,assistant.key]
  key=hashlib.sha256(json.dumps(identity).encode()).hexdigest()
  immediate=None;prepared=None
  with self.lock:
   if component!='reports' and hasattr(assistant,'explain_proposal'):
    from .proposal_narrative import prepare,immediate as explanation
    if key not in self.contexts:
     captured=deepcopy(state)
     self.contexts[key]=prepare(captured,component,lambda sku:evidence(captured,sku))
    prepared=self.contexts[key];immediate=explanation(prepared)
   future=self.jobs.get(key)
   if future is None:
    snapshot=deepcopy(state)
    question=('Giải thích ngắn gọn kế hoạch M2 hiện tại: phân biệt dự báo gốc và lượng chuẩn bị sau policy; nêu vì sao có buffer, rủi ro dư hàng và mục tiêu tồn 21:30.' if component=='m2' else
     'Giải thích đề xuất giá M1 tại checkpoint hiện tại, dùng tồn, bán 30/60 phút, tốc độ bán và giá hiện hành. Nếu giữ giá, nói rõ không cần quản lý duyệt. Nếu đổi giá, nêu SKU, phần trăm và số tiền, giải thích dựa trên dữ liệu; không bịa uplift.')
    question+=' Trình bày tối đa 120 từ, 3 ý ngắn. Không khẳng định bảo đảm tồn 21:30.'
    if component=='reports':
     captured=deepcopy(report_context)
     question='Phân tích báo cáo '+captured['scope']['section']+' cho SKU '+captured['scope']['sku']+'. Gọi get_business_report rồi trả JSON insights và actions đúng schema. Chọn khoảng năm fact_key phù hợp: doanh thu/lượng bán, giá thực thu và chiết khấu, món dư, hiệu quả giá, so sánh và hành động ưu tiên. Commentary chỉ nhận xét định tính, không chứa chữ số, ngày hoặc giờ; máy chủ chèn số liệu verified_facts. Không quy kết quan hệ nhân quả hoặc gọi tồn là hủy. Với SKU riêng chỉ phân tích SKU đó.'
     future=self.report_pool.submit(assistant.chat,question,snapshot,lambda sku:evidence(snapshot,sku),captured)
    elif prepared is not None:future=self.pool.submit(assistant.explain_proposal,prepared)
    else:future=self.pool.submit(assistant.chat,question,snapshot,lambda sku:evidence(snapshot,sku))
    self.jobs[key]=(future,snapshot['minute'])
    if len(self.jobs)>128:
     for k,(job,_) in list(self.jobs.items()):
      if k!=key and job.done():del self.jobs[k];self.contexts.pop(k,None);break
   else:future,_=future
   future,minute=self.jobs[key]
  if not future.done():return dict(status='running',as_of_minute=minute,component=component,answer=immediate,evidence_ready=bool(immediate),ai_status='running')
  try:
   result=future.result()
   return dict(status='ready',as_of_minute=report_context['as_of_minute'] if report_context is not None else minute,as_of_day=report_context['selected_day'] if report_context is not None else state.get('day'),component=component,answer=result['answer'],provider=result['provider'],model=result['model'],tools_used=result['tools_used'],ai_status='ready')
  except Exception as exc:
   if immediate:return dict(status='ready',as_of_minute=minute,component=component,answer=immediate,evidence_ready=True,ai_status='unavailable',delivery='VERIFIED_FACTS_FALLBACK',error='Copilot tạm thời chưa tổng hợp được; lời giải thích bên dưới lấy trực tiếp từ bằng chứng của đề xuất.')
   return dict(status='unavailable',as_of_minute=minute,component=component,error=str(exc))
