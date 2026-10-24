from pathlib import Path
import csv,json,shutil,hashlib,subprocess,sys
R=Path(__file__).resolve().parents[2];O=R/'deliverable/SmartFresh_V607';B=O/'01_ORIGINAL_BASELINE_PRIVATE';T=O/'02_TRAIN_VALIDATION';E=O/'03_TEST_POS_RUNTIME';D=O/'04_GUIDE_DICTIONARY_SOURCES'
def read(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows):
 with open(p,'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
# Compatibility filename contains observed columns ONLY. Hidden labels stay elsewhere.
shutil.copy2(B/'baseline_development_OBSERVED.csv',B/'baseline_development_FULL_SCORER_ONLY.csv')
p=E/'code/pos_core.py';s=p.read_text();s=s.replace("def round1000(v):return int((Decimal(str(v))/1000).quantize(Decimal('1'),rounding=ROUND_HALF_UP))\n",'').replace(' or False','')
s=s.replace(" if requested==0 and floor==0:\n  # HOLD an already approved cash price rather than restoring the list price.\n  cash=integer(current_price) if current_price is not None else p\n  q=quote_cash_price(p,cash,current_price,floor);q['requested_discount_pct']=0;return q", " if requested==0:\n  cash=integer(current_price) if current_price is not None else p\n  try:\n   q=quote_cash_price(p,cash,current_price,floor);q['requested_discount_pct']=0;return q\n  except ValueError:pass")
s=s.replace("   changes=sum(1 for e in self.price_events if e['date']==self.day and e['branch']==b and e['sku_code']==s and e['price_version']>0 and e['approved_unit_price_vnd']<spec['unit_price_vnd_reference'])\n",'')
p.write_text(s)
p=E/'code/pos_core.py';s=p.read_text();needle=' def _open(self):'
batch_code=''' def schedule_batch(self,b,sku,qty,ready_time):
  if self.phase!='OPEN' or b not in ('M2_ONLY','JOINT_M1_M2'):raise ValueError('Only open M2 branches can schedule adaptive production')
  if sku not in self.master:raise ValueError('Unknown SKU')
  st=self.states[b,sku]
  batch=dict(qty=integer(qty),order_time=self.time,ready_time=ready_time)
  plan=deepcopy(st.plan);plan['production_batches'].append(batch)
  checked=self._validate_plan(sku,plan)
  st.plan=checked;st.batches.append(batch);self.plans[b,sku]=deepcopy(checked)
  self.audit.append(dict(event='ADAPTIVE_BATCH_COMMITTED',date=self.day,time=self.time,branch=b,sku_code=sku,production_batch=deepcopy(batch)))
  return deepcopy(batch)
'''
if ' def schedule_batch(' not in s:s=s.replace(needle,batch_code+needle)
p.write_text(s)
p=E/'code/pos_server.py';s=p.read_text().replace("('/api/prepare','/api/propose')","('/api/prepare','/api/propose','/api/production')").replace("integer(data['requested_discount_pct']) if", "float(data['requested_discount_pct']) if")
needle="      if path=='/api/prepare':"
s=s.replace(needle,"      if path=='/api/production':return self.send(200,session.schedule_batch(branch,data['sku_code'],data['qty'],data['ready_time']))\n"+needle)
p.write_text(s)
p=E/'code/score_private.py';s=p.read_text().replace("-int(float(r['disposal_cost_vnd_assumed'])) for r in rs)","-int(float(r['disposal_cost_vnd_assumed']))-int(float(r.get('markdown_operations_cost_vnd_assumed',0))) for r in rs)")
s=s.replace("'SUPPLIED_COSTS_VERIFY_PROVENANCE'","'ASSUMED_COMPONENT_COSTS_NOT_ACTUAL_AEON_PROFIT'")
s=s.replace("r['delta_revenue_vs_baseline_vnd']=", "r['delta_contribution_vs_baseline_vnd_assumed']=r['contribution_vnd_if_costs_supplied']-baseline['contribution_vnd_if_costs_supplied'] if r['contribution_vnd_if_costs_supplied'] is not None and baseline['contribution_vnd_if_costs_supplied'] is not None else None\n  r['delta_revenue_vs_baseline_vnd']=")
p.write_text(s)
# Additional acceptance tests use fabricated mechanics fixtures, never held-out customer data.
p=E/'code/test_v607.py';p.write_text('''import unittest
from test_pos import fixtures,until,SKU
from pos_core import Session,quote_price
class NewMechanics(unittest.TestCase):
 def test_nonround_approval_receipt(self):
  m,c,s,h=fixtures();x=Session(m,c,s,h);until(x,'20:00');p=x.propose_price('M1_ONLY',SKU,approved_cash_price_vnd=27195);x.approve(p['id']);x.advance();self.assertEqual(x.states['M1_ONLY',SKU].pos[-1]['unit_price_vnd'],27195)
 def test_adaptive_batch_and_causality(self):
  m,c,s,h=fixtures(0);x=Session(m,c,s,h);until(x,'16:00');before=x.states['M2_ONLY',SKU].inventory;x.schedule_batch('M2_ONLY',SKU,8,'17:00');self.assertEqual(x.states['M2_ONLY',SKU].inventory,before);until(x,'17:00');self.assertEqual(x.states['M2_ONLY',SKU].inventory,before+8)
  with self.assertRaises(ValueError):x.schedule_batch('BASELINE',SKU,8,'18:00')
  with self.assertRaises(ValueError):x.schedule_batch('M2_ONLY',SKU,8,'17:15')
 def test_weekly_order_does_not_use_today(self):
  m,c,s,h=fixtures();x=Session(m,c,s,h);q=x.baseline_qty('BASELINE',SKU);x.hist['BASELINE',SKU].append(dict(h[-1],date=x.day,sold_qty=99999));self.assertEqual(q,x.baseline_qty('BASELINE',SKU))
 def test_no_double_count_waste(self):
  m,c,s,h=fixtures(0);s[SKU]['markdown_action_cost_vnd_assumed']=350;x=Session(m,c,s,h);until(x,'22:00')
  for r in x.observed_daily:self.assertEqual(r['contribution_vnd_assumed'],r['revenue_vnd']-r['production_cost_vnd_assumed']-r['disposal_cost_vnd_assumed']-r['markdown_operations_cost_vnd_assumed'])
if __name__=='__main__':unittest.main(verbosity=2)
''')
p=E/'code/freeze_submission.py';p.write_text(p.read_text().replace('V606_','V607_'))
p=E/'code/test_pos.py';s=p.read_text().replace('from pos_core import Session,quote_price,BRANCHES','from pos_core import Session,quote_price,quote_cash_price,BRANCHES')
s=s.replace('test_01_all_money_whole1000_and_bound','test_01_integer_money_and_bound').replace("self.assertEqual(q['approved_unit_price_vnd']%1000,0)","self.assertIsInstance(q['approved_unit_price_vnd'],int)").replace("self.assertEqual(quote_price(25000,50)['approved_unit_price_vnd'],13000)","self.assertEqual(quote_price(25000,50)['approved_unit_price_vnd'],12500)\n  self.assertEqual(quote_price(29400,7.5)['approved_unit_price_vnd'],27195)\n  self.assertEqual(quote_cash_price(27400,23000)['approved_unit_price_vnd'],23000)\n  self.assertEqual(quote_price(27400,0,23000,100*(27400-23000)/27400)['approved_unit_price_vnd'],23000)\n  with self.assertRaises(ValueError):quote_cash_price(24500,12249)")
p.write_text(s)
# Fit-only randomized rollouts are grouped by original date. Scenario is an audit group, not a predictor.
xp=T/'fit/EXPLORATION_ASSUMED'
(xp/'READ_ME.md').write_text('''# Chỉ là trải nghiệm từ simulator
15.540 trạng thái thuộc 111 ngày nguồn × 7 SKU × 5 mốc × 4 giả định phản ứng giá. Không phải 444 ngày độc lập, không phải thử nghiệm tại AEON.
Nối ba bảng bằng sample_id. Features chỉ lấy allowlist m1_pre_action_columns; sample_id/scenario_id/source_date_group/decision_at/evidence_status dùng kiểm toán/nhóm, không làm predictor. Hành động là treatment, outcome là nhãn tương lai.
behavior_propensity là xác suất có điều kiện tại trạng thái của hành vi chọn đều trong tập giá khả thi; không phải xác suất thực của nhân viên AEON. Chỉ áp dụng trong simulator này. Stockout vẫn censor outcome.
Chia theo ngày gốc; mọi phiên bản một ngày đi cùng một fold. Không chọn nhãn “giá tối ưu” từ nhu cầu ẩn. Kiểm tra HOLD trong kịch bản null. Không được suy ra hiệu ứng giảm sớm thực tế từ các nhãn giả lập này.
''',encoding='utf8')
sources=[
 ('FRENCH_RAW','https://www.kaggle.com/datasets/matthieugimbert/french-bakery-daily-sales','234005 raw rows preserved; 233 open dates Jan-Aug2022; seven explicit source articles','Not AEON POS; historical sales are imperfect demand proxy'),
 ('USER_SURVEY','USER_CONVERSATION','7 exact list prices and5 conditional markdown cash prices','Survey date/barcodes/receipts unknown; current prices applied to2022 scenario'),
 ('AEON_IBM','https://jp.newsroom.ibm.com/2024-05-07-AEON-RETAIL-AI-Kakaku-and-AI-Order-developped-with-IBM-Japan','Design rationale joint ordering and markdown using sales/weather/footfall','Japanese retailer departments; NOT TanPhu costs or expected performance'),
 ('GREEN_AI','https://github.com/Green-AI-Hub-Mittelstand/Reduce-Foodwaste-Dataset','Downloaded train.csv; audited5142rows; rejected quantitative waste-ratio calibration','Scaled negative values; sales+unsold !=ordered; no complete rows before2022'),
 ('PURATOS','https://www.puratos.com.au/en/recipes/danish','Process benchmark:60-80min proof plus16min bake;120min scenario lead from prepared dough','Not AEON recipe; no validated physical capacity; from-scratch process longer'),
 ('FLOUR','https://www.beemart.vn/bot-my-dia-cau-1kg','Retail quote23000VND/kg; ingredient anchor','Not AEON procurement price'),
 ('BUTTER','https://www.beemart.vn/bo-sua','Retail quote1550000VND/5kg=>310000VND/kg','Not AEON procurement price'),
 ('CHEESE','https://www.beemart.vn/pho-mai-kem-anchor-1kg','Retail quote249000VND/kg; ingredient anchor','Not AEON procurement price'),
 ('WAGE','https://baochinhphu.vn/tang-luong-toi-thieu-vung-tu-1-1-2026-102251110175033018.htm','Published2026RegionI25500VND/hour used only low scenario anchor','Actual labor wage/load/productivity unknown; not2022 wage'),
 ('EVN','https://www.evn.com.vn/d/vi-VN/news/Bieu-gia-ban-le-dien-theo-Quyet-dinh-so-1279QD-BCT-ngay-0952025-cua-Bo-Cong-Thuong-60-28-502668','2025business<6kV benchmark1918/3152/5422VND/kWh verified image','Not verified AEON contract/voltage/time mix; not2022 tariff'),
 ('DISPOSAL_REJECTED','https://www.congbao.hochiminhcity.gov.vn/cong-bao/van-ban/quyet-dinh/so/67-2025-qd-ubnd/ngay/07-05-2025/noi-dung/47910/48000','Located decision but failed to retrieve primary contents; no rate imported','50/150/400VND per unit disposal are ASSUMED total handling/transport scenarios'),
 ('WEATHER','https://open-meteo.com/en/docs/historical-weather-api','Inherited historical hourly weather; previous-day aggregates only in modelfeatures','No issued JMA forecast; observed rainfall used only by private simulator'),
 ('BREAD_STUDY','https://research.slu.se/en/publications/quantification-and-economic-assessment-of-surplus-bread-in-italia/','Context only: empirical surplus varies; not used to force waste target','Bread samples inItaly not Vietnamese pastry waste benchmark')]
write(D/'sources_and_build_use.csv',[dict(source_id=i,url=url,actual_use=use,not_supported=limit,accessed_on='2026-10-23') for i,url,use,limit in sources])
donor=read(R/'work/v607/donor_train.csv');complete=[r for r in donor if all(r[k] for k in ('sales','unsold','ordered'))]
(D/'donor_audit.json').write_text(json.dumps(dict(rows=len(donor),complete_supply_rows=len(complete),earliest_complete_supply_date=min(r['date'] for r in complete),negative_values_present=True,unit_balance_valid=False,decision='REJECT_RATIO_CALIBRATION',sha256=hashlib.sha256((R/'work/v607/donor_train.csv').read_bytes()).hexdigest()),indent=2))
shutil.copy2(R/'work/v607/donor_train.csv',B/'supplementary_donor_train_NOT_FOR_MODEL.csv')
stats=json.loads((D/'BUILD_STATS.json').read_text());rows=read(B/'baseline_development_OBSERVED.csv');costs={r['sku_code']:r for r in read(D/'cost_components_ASSUMED.csv')}
sense=[]
for scenario in ('low','central','high'):
 for split,lo,hi in [('fit','2022-01-02','2022-04-30'),('validation','2022-05-01','2022-06-30')]:
  z=[r for r in rows if lo<=r['date']<=hi];production=sum(int(r['prepared_qty'])*int(costs[r['sku_code']]['production_'+scenario+'_vnd_assumed']) for r in z);disposal=sum(int(r['waste_qty'])*int(costs[r['sku_code']]['disposal_'+scenario+'_vnd_assumed']) for r in z);revenue=sum(int(r['revenue_vnd']) for r in z);ops=sum(int(r['markdown_operations_cost_vnd_assumed']) for r in z)
  sense.append(dict(split=split,cost_scenario=scenario,revenue_vnd=revenue,production_vnd_assumed=production,disposal_vnd_assumed=disposal,markdown_ops_vnd_assumed=ops,contribution_vnd_assumed=revenue-production-disposal-ops))
write(D/'cost_sensitivity_development.csv',sense)
sku_audit=[]
for sku in costs:
 z=[r for r in rows if r['sku_code']==sku];sku_audit.append(dict(sku_code=sku,sku_days=len(z),sold=sum(int(r['sold_qty']) for r in z),waste=sum(int(r['waste_qty']) for r in z),censored_rate=sum(int(r['censored_demand_flag']) for r in z)/len(z)))
write(D/'sku_development_audit.csv',sku_audit)
guide='''# SmartFresh V6.07 — dữ liệu, POS và cách dùng

## Trạng thái phát hành
Đã xây lại dữ liệu và runtime; chưa train M1/M2, chưa chạy/chấm test chính thức. 233 ngày nguồn, 7 SKU khảo sát; không thêm ngày giả. Đây là mô phỏng nghiên cứu có truy xuất nguồn, không phải POS, định mức hay kết quả lợi nhuận AEON Tân Phú đã đo.

## Mở file nào?
| Gói | Công dụng | Quyền model |
|---|---|---|
| 01_ORIGINAL_BASELINE_PRIVATE | Nguồn French nguyên bản, ánh xạ từng dòng, luồng khách test, baseline phát triển và nhãn chấm ẩn | Không cấp cho model/agent train. Custodian giữ trên máy hoặc tài khoản riêng |
| 02_TRAIN_VALIDATION | fit để huấn luyện; validation để chọn mô hình/chính sách; exploration giả lập nằm riêng trong fit | Chỉ lấy cột feature theo feature_contract; labels dùng giám sát đúng vai trò |
| 03_TEST_POS_RUNTIME | POS, master, lịch và seed quan sát đến30/6; API theo nhánh, mã khóa submission và scorer | Model chỉ nhận API đúng thời điểm; manager token và filesystem01 không được cấp |
| 04_GUIDE_DICTIONARY_SOURCES | Báo cáo build, từ điển, nguồn, đối chiếu chi phí và QA | Tài liệu, không nối toàn bộ thành feature |

Fit:111 ngày02/01–30/04/2022 (777 SKU-ngày). Validation:60 ngày01/05–30/06 (420). Test:62 ngày01/07–31/08 (434). Tổng1631 SKU-ngày. Những ngày nguồn đóng cửa/không có dữ liệu không được bổ sung số0. Warmup tháng12/2021 nằm ngoài233 ngày mục tiêu, chỉ dùng lịch sử trước quyết định.

## Giá và ánh xạ
Giữ giá khảo sát:29.400;25.000;25.000;25.000;24.500;27.400;27.400 VND. Ba Danish có giá khi ế20.000, croissant20.000, crepe23.000. Hai SKU còn lại chưa có giá markdown khảo sát nên baseline giả định HOLD; AI được đề xuất giảm nếu có căn cứ. Giá được phép lẻ tới1VND, mức giảm thực tế tối đa50%. Giá hiện tại áp lên lịch proxy2022 để so chính sách, không tuyên bố là giáAEON2022.

Đã bỏ chia đều pooled demand. Bảng sku_proxy_crosswalk.csv giữ7 chuỗi French riêng: CROISSANT, PAIN AUX RAISINS, CHAUSSON AUX POMMES, CROISSANT AMANDES, PAIN AU CHOCOLAT, ECLAIR, TARTELETTE. Ánh xạ theo nhóm bánh là yếu, đặc biệt ECLAIR→crepe và TARTELETTE→red velvet; không phải cùng sản phẩm hoặc ước lượng thị phần AEON. Không có nhân đôi toàn bộ lượng bán như bản trước. Giữ raw không chỉnh; mỗi dòng sinh ra số lượng kịch bản có lineage riêng.

## Cuối tuần, buổi tối, thời tiết
Chuẩn hóa hiệu ứng thứ của proxy bằng tháng12/2021, có shrinkage4 quan sát để tránh quá khớp. Áp profile địa phương giả định T2–CN:1,1,1,1.05,1.10,1.35,1.40 dựa trên quan sát định tính của người dùng. Đây không phải hệ số ước lượng từ AEON. 75% xác suất phân bổ đơn vị vào17–22h là giả định; phân bổ bằng SHA256 cố định, không giữ giờ giao dịch French nguyên trạng. Không suy ra số khách toàn khu bakery từ7 món này.
Kiểm tra trên171 ngày phát triển: bán trung bình T5≈69,T6≈66,T7≈106,CN≈157 đơn vị/ngày của7SKU. Đây là kết quả kịch bản, không phải số khách thực. Không ép mọi thứ7 phải cao hơn mọi thứ6: mưa, sự kiện, biến động và hết hàng có thể đảo thứ tự từng ngày. Cần chấm riêng nhu cầu và bán được; model không được nhìn nhu cầu ẩn.
Mưa thực tế ngày≥10mm làm cầu kịch bản×0.95; lễ×1.10, cậnTết×1.15, đều ASSUMED và chưa SKU-aware về hệ số. Chưa đủ bằng chứng để fit hiệu ứng thực tạiAEON. Model sáng chỉ thấy tổng thời tiết ngày trước, không gọi đó là JMA forecast. Dữ liệu forecast phát hành đúng thời điểm chưa có.

## Baseline và bài toán hàng dư
Lượng chuẩn bị baseline chốt theo tuần: lịch sử trước thứ2, tối đa28 quan sát; ưu tiên cùng thứ (ít nhất2), trung bình bán đã khử hệ số lễ +0.5 độ lệch chuẩn, rồi nhân hệ số ngày hiện tại và làm tròn theo mẻ4. Censorbuffer dùng lượng chuẩn bị quá khứ khi ít nhất nửa quan sát bị censor. Không nhìn cầu tương lai. Đây là baseline vận hành giả định; chưa có nguồn xác nhận AEON Tân Phú đặt cố định theo tuần hay dùng công thức này.
21:00 tính nguy cơ dư từ tồn và tốc độ30/60phút; chỉ áp giá giảm khảo sát nếu nguy cơ đủ lớn. Món bán nhanh có thể HOLD. Baseline giữ mức này tới22:00. Không giảm đồng loạt30%/50%.
Đây không phải cách “làm xấu baseline cho AI thắng”: phương pháp và tham số được ghi lại trước khi train/test; không chọn lại sau khi xem kết quảAI. Tồn lớn ởSKU chậm và hết hàng ởSKU nhanh có thể cùng xảy ra. Báo cáo cả hai, không chỉ tổng hủy.

## M1 khác baseline ở đâu?
Baseline data vẫn ghi đúng lịch baseline. Không sửa lịch sử thành hành động giảm sớm đã từng xảy ra. Bổ sung EXPLORATION_ASSUMED riêng:4 kịch bản phản ứng null/weak/central/strong, mỗi kịch bản111 ngày nguồn,7SKU,5mốc19:30–21:30. Tổng15.540 trạng thái;4.015 lần tăng giảm trước21:00. Đây là trải nghiệm simulator, không làm số ngày nguồn tăng lên444.
Hành vi chọn đều trong tập giá khả thi, chỉ mở thêm markdown khi tồn vượt lượng bán tiếp suy ra từ pace; HOLD luôn hợp lệ. Ghi propensity, actionprice, pre-actionfeatures và next30 outcome riêng. Gate này giới hạn vùng exploration; không có bằng chứng cho trạng thái không được thử. Không gán nhãn optimalprice từ hidden demand. Scenario_id và sample_id không phải predictor. Chia fold theo ngày gốc, không random-row giữa các bản sao kịch bản.
Khách có ý định mua giá gốc và pool nhạy giá được giữ chung giữa4 nhánh; pool bằng1×baseintent là giả định, xác suất mua thêm=strength×effective_discount/100. Không có dữ liệu xác nhận elasticityAEON; chưa mô phỏng chuyểnSKU, khách đợi giảm giá, cannibalization hay giới hạn giỏ hàng. Nullscenario giúp thấy giảm sớm có thể giảm lãi. Không dùng kết quả này để tuyên bố quan hệ nhân quả ngoài thực tế.
M1 có thể dùng doanh số quan sát sau hành động để học response trong giả định; bộ tối ưu so lãi kỳ vọng HOLD với các giá khác, tính mất doanh thu trên khách vốn sẽ mua giá gốc. Không bắt buộc giảm từ19:30, không cần bước đều, không tăng giá sau khi đã giảm. Mức sau21h không được thấp hơn tem baseline được công bố cho chính nhánh đó. RuleC tối thiểu30phút giữa các lần đổi giá. TênA/B/C trong code là cách diễn giải hiện tại; chưa có văn bản rule đầy đủ độc lập của doanh nghiệp.

## Chi phí — có nguồn đến đâu?
cost_components_ASSUMED.csv cho từngSKU có bột/bơ/creamcheese, phần nguyên liệu còn lại, yield, phút lao động, kWh, bao bì và dải thấp/trung tâm/cao. Giá bột23.000/kg,bơ310.000/kg,creamcheese249.000/kg là giá bán lẻ công khai, không phải giá mua sỉAEON. Gram nguyên liệu và định mức lao động/điện là giả định, đặc biệtcrepe/redvelvet có thể là hàng mua từ nhà cung cấp nên không được coi BOM giả lập là giá nhập thật.
Lương25.500đ/giờ là mốc tối thiểu vùngI2026 tham khảo; trung tâm35.000, cao50.000 là giả định. Điện dùng benchmarkkinhdoanh<6kV củaEVN2025:1.918/3.152/5.422đ/kWh; chưa xác nhận hợp đồng điện trung tâm, không tuyên bố đây là chi phí2022. Phí hủy50/150/400đ mỗi đơn vị là giả định xử lý+vận chuyển; chưa có hợp đồng xử lý rácAEON. Không lấy con số chưa kiểm chứng từ quyết định67 làm chi phí thật.
Lãi góp kịch bản = doanh thu thực thu − chi phí toàn bộ lượng chuẩn bị − phí hủy bổ sung − phí đổi tem. Chi phí đổi tem350đ/lần/SKU là giả định, chưa là mô hình lao động theo từng tem. Chi phí sản xuất phần hủy là khoản con của chi phí chuẩn bị, KHÔNG trừ lần thứhai. Chi phí mặt bằng/quản lý/cố định, thuế, công suất dùng chung và phíAI chưa đầy đủ; không gọi đây là lãi ròng kế toán. Với quyết định tối đã nướng, chi phí sản xuất đã chìm; không dùng nó để cấm bán giá thấp nếu bán tốt hơn hủy về lãi tăng thêm.

## Kết quả kiểm tra dữ liệu phát triển — chưa phải thành tíchAI
Fit:11.544 chuẩn bị,8.594 bán,2.950 dư; chi phí sản xuất phần dư giả định34.274.364đ, xử lý442.500đ.
Validation:5.940 chuẩn bị,5.170 bán,770 dư; chi phí sản xuất phần dư giả định8.702.665đ, xử lý115.500đ.
Tổng chi phí phần dư theo kịch bản trung tâm≈43,54triệu trên171 ngày, phần lớn là sản xuất. Không cần thổi phí hủy để làm lớn bài toán. Tỷ lệ dư khá cao (25,55%fit;12,96%validation) không phải tỷ lệ hủy thựcAEON và chưa được hiệu chuẩn bằng số liệu cửa hàng. Xem dải chi phí trong cost_sensitivity_development.csv, không chọn một con số như “sự thật”.
Censor vẫn nghiêm trọng:286/777fit và218/420validation. Vì vậy bản này chưa giải quyết xong nhu cầu bị che khuất, chưa cam kết phục vụ97%. Chỉ dùng sold làm lowerbound khi censor, không gán true demand=sold. Các công cụ censored cũ là diagnostics; chưa train mô hình censoraware mới. CoverageTết validation/test vẫn thiếu; dùng OODfallback, không tuyên bố đã kiểm địnhTết.

## POS vận hành và vòng lặp test
Giải nén01và03 thành hai thư mục cạnh nhau; chạy03/RUN_POS_DEMO_WINDOWS.bat hoặc sh run_pos_demo.sh. Demo chỉ dùng15/6, không chạm test. MởURL được in, dùng manager token do server sinh. Chỉ giao token đúng nhánh cho model. Dữ liệu mô phỏng theo bước15phút, sinh timestamp giao dịch trong khoảng, checkpoint quyết định30phút; chưa phải hệ thống streaming giây thật.
06:00 M2 gửi kế hoạch initial_qty và các mẻ order_time/ready_time; FROZEN không có kế hoạchM2 thì không mở bán. Lượng đầu ngày củaM2 không bị lấy cố định từ filebaseline. Trong ngày, tồn quầy/tồn sau và refill được cập nhật riêng. 19:30,20:00,20:30,21:00,21:30 M1 đề xuất; chưa duyệt thì giữgiá cũ. Sau duyệt, UI và giao dịch mới dùng đúng cashprice, không sửa hóa đơn cũ. Cuối ngày mỗi nhánh tự ghi lịch sử bán/censor/tồn của mình để dự báo ngày tiếp theo.
Baseline/M1only dùng baselineordering; M2only/Joint dùng M2; pricingbaseline dùng vớiBaseline/M2only và làm floor tại21h cho nhánhAI. Cùng luồng khách và số ngẫu nhiên, nhưng mỗi nhánh có tồn, giá, bán và lịch sử riêng.
Lead120phút là giả định từ dough đã chuẩn bị (benchmarkproof+bake), không phải từ nguyên liệu thô. Công suất được neo preperiod nhưng chưa có lò chung/hàng đợi, hao hụt nướng, năng lực nhân sự hoặc hạn dùng thật. Refill hiện là chuyển kho sau→quầy tại ngưỡng, không có độ trễ nhân viên. Mẻ bổ sung đặt trong kế hoạch sáng, chưa cóAPIđặt mẻ thích ứng giữa ngày. Sản phẩm packaged đang giả định hết hạn cuối ngày; cần thay bằnglot/expiry thực trước triển khai.

## Train, validation, chọn model và blind test
TrainM2 bằngfit, nhãn censored-aware; fit các encoder/scale/imputation trênfit. Lagmissing giữ cờmissing và fallback từ lịch sử có thật, không điền nhu cầu0. TrainM1 tách logbaseline với explorationgiả định. Chọn chính sách trênvalidation theo lãi góp, hủy vàlostsales/service đồng thời; dùng Pareto và giới hạn mấtbán do nhóm dự án chốt TRƯỚCtest, không mặc định97%.
Chưa có model đã train trong gói này. Adapter mẫu cố ý NotImplemented; phải nối model mới, khóa weights/preprocessing/config/runtime bằngfreeze_submission.py rồi chạyFROZEN. Không dùng modelV606 cũ như thể tương thích bộnguồn/cost mới. score_private.py chỉ chấm sau khi hoàn tất đủ4nhánh×434SKU-ngày; xuấtlãi vàdoanhthu chênhbaseline.
Testkhép kín không đồng nghĩa retrain ngay:weights khóa, featurehistory thay đổi từng ngày. Champion/challenger online cần protocolriêng: chỉ dùng ngày đã đóng, validationnội bộ quákhứ, lịchretrain và tiêu chíthaychampion định trước. Runtime hiện chưa tựtrain/retrain.
Chỉ táchfolder không tạo blindtest. Custodian phải giữ01/scorer/manager token riêng, modelprocess không quyền đọc những file đó. Khóa trướcseed/thếgiới/cost/rules, không xem kết quảtest để chỉnhsimulator hoặc chọnmodel. Testởđây là đánhgiámôphỏng được côlập; nguồnproxy côngkhai và kỳđã nghiêncứu trước không trởthành holdoutAEONmới hoàn toàn. Đổi seed không xóa thiênlệch nghiêncứu. Chưa chạytestchínhthức trong lầnbuildnày.

## Nguồn bổ trợ được dùng thế nào?
sources_and_build_use.csv ghiURL,vai trò,giới hạn. CaseAEON–IBM hỗtrợ hướng phối hợpđặt hàng/markdown, không gán kết quảNhật choTânPhú. DonorGreenAI cóordered/unsold nhưngđãscale, cóâm vàkhôngbảo toànunits: đã loại khỏi hiệu chuẩn tỷlệhủy; audit vàhash đi kèm. Không lấy tỷ lệ giả để “chứng minh”AI cólợi.
Muốn kếtluận lợi nhuậnthật cần bổ sung: số chuẩn bị/bán/hủy theoSKU-ngày, hóađơnnguyênliệu/giánhập, logtemgiá/phêduyệt, timestampstockout/refill, quy cáchmẻ/côngsuất/hạnsửdụng và thínghiệmgiá cóđối chứng. Dữliệu cónguồnhiện tại chỉ hỗtrợ nghiêncứu độnhạy, không bảo đảmAI thắng.
'''
guide=guide.replace('Mẻ bổ sung đặt trong kế hoạch sáng, chưa cóAPIđặt mẻ thích ứng giữa ngày.', 'Có thể đặt mẻ từ kế hoạch sáng hoặc gọi POST /api/production giữa ngày với branch,sku_code,qty,ready_time. API chỉ cho nhánhM2, lấy order_time đúng đồng hồ hiện tại, kiểm tra leadtime/capacity/mẻ/hạn chót; hàng chỉ vào tồn khi ready. Adapter mẫu chưa tự gọi API này: mô hình hoặc bộ điều phối cần quyết định từ context đã quan sát.')
(D/'START_HERE.md').write_text(guide,encoding='utf8');(O/'START_HERE.md').write_text(guide,encoding='utf8');(R/'deliverable/SmartFresh_V607_HuongDan.md').write_text(guide,encoding='utf8')
# Dictionary retains detailed known definitions and covers every exported CSV field.
old=read(R/'deliverable/SmartFresh_V606/04_GUIDE_DICTIONARY_SOURCES/data_dictionary.csv');known={r['field']:r['definition_vi'] for r in old}
known.update(sample_id='Khóa ghép feature/treatment/outcome; không dùng làm predictor.',scenario_id='Nhóm giả định phản ứng giá; không phải feature cửa hàng.',source_date_group='Ngày nguồn để gom mọi bản sao vào cùng fold.',behavior_propensity='Xác suất chọn hành động có điều kiện trong tập giá khả thi của logger giả lập.',feasible_price_set_json='Tập giá được phép tại trạng thái trước hành động; JSON array VND.',action_price_vnd='Giá của hành động được duyệt; treatment, không phải feature trước hành động.',action_discount_pct='100*(list-price)/list của hành động; treatment.',wasted_production_cost_vnd_assumed='Chi phí sản xuất phân bổ cho hàng dư; là phần con chi phí sản xuất, không trừ hai lần.',contribution_vnd_assumed='Doanh thu trừ sản xuất toàn bộ, phí hủy, đổi tem theo định mức giả định.',markdown_operations_cost_vnd_assumed='350VND giả định cho mỗi lần đổi giá thực/SKU.',censored_next30='1 nếu hết tổng tồn ở một khoảng trong cửa sổnhãn; doanh số là lowerbound.',source_article='Tên sản phẩm French gốc, không phải barcodeAEON.',weekday_factor_assumed='Profile thứ địa phương chia hiệu ứng thứ preperiod đãshrink; giả định.')
dictionary=[]
for p in sorted(O.rglob('*.csv')):
 if p.name=='data_dictionary.csv':continue
 with p.open(encoding='utf-8-sig',newline='') as f:fields=next(csv.reader(f))
 for field in fields:
  private='01_' in str(p);label=('LABEL' in p.name or 'targets' in p.name);action='TREATMENT' in p.name
  role='CUSTODIAN_ONLY' if private else 'LABEL_NOT_FEATURE' if label else 'ACTION_NOT_FEATURE' if action else 'FEATURE_ONLY_IF_ALLOWLISTED_OR_METADATA'
  meaning=known.get(field,('Tham số/chi phí mô phỏng giả định; xem cost_components và hướng dẫn.' if 'assumed' in field else 'Trường dữ liệu/kiểm toán; xem định nghĩa bảng và phương pháp build, không tự đưa vào predictor.'))
  dictionary.append(dict(file=str(p.relative_to(O)),field=field,unit='VND' if 'vnd' in field else 'percent' if 'pct' in field else 'see_definition',allowed_role=role,definition_vi=meaning,availability='PRIVATE' if private else 'AFTER_OUTCOME_WINDOW' if label else 'AS_OF_DECISION_OR_STATIC_METADATA',null_policy='Unknown/not available; never automatically replace demand with0'))
write(D/'data_dictionary.csv',dictionary)
# Build scripts packaged as source, paths documented for reproducibility from prior immutable release.
shutil.copy2(R/'work/v607/build.py',D/'build.py');shutil.copy2(R/'work/v607/finish.py',D/'finish.py')
(D/'REBUILD.md').write_text('Build scripts resolve workspace root from work/v607. Requires immutable deliverable/SmartFresh_V606 plus work/v607/donor_train.csv. Run build.py then finish.py then qa.py. No model training or official test evaluation. SHA256SUMS authenticates packaged files; earlier release must be retained. The source table and build script expose all scenario assumptions.\n')
print('Finished documentation and runtime patches')
