# SmartFresh V6.07 — dữ liệu, POS và cách dùng

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
Lead120phút là giả định từ dough đã chuẩn bị (benchmarkproof+bake), không phải từ nguyên liệu thô. Công suất được neo preperiod nhưng chưa có lò chung/hàng đợi, hao hụt nướng, năng lực nhân sự hoặc hạn dùng thật. Refill hiện là chuyển kho sau→quầy tại ngưỡng, không có độ trễ nhân viên. Có thể đặt mẻ từ kế hoạch sáng hoặc gọi POST /api/production giữa ngày với branch,sku_code,qty,ready_time. API chỉ cho nhánhM2, lấy order_time đúng đồng hồ hiện tại, kiểm tra leadtime/capacity/mẻ/hạn chót; hàng chỉ vào tồn khi ready. Adapter mẫu chưa tự gọi API này: mô hình hoặc bộ điều phối cần quyết định từ context đã quan sát. Sản phẩm packaged đang giả định hết hạn cuối ngày; cần thay bằnglot/expiry thực trước triển khai.

## Train, validation, chọn model và blind test
TrainM2 bằngfit, nhãn censored-aware; fit các encoder/scale/imputation trênfit. Lagmissing giữ cờmissing và fallback từ lịch sử có thật, không điền nhu cầu0. TrainM1 tách logbaseline với explorationgiả định. Chọn chính sách trênvalidation theo lãi góp, hủy vàlostsales/service đồng thời; dùng Pareto và giới hạn mấtbán do nhóm dự án chốt TRƯỚCtest, không mặc định97%.
Chưa có model đã train trong gói này. Adapter mẫu cố ý NotImplemented; phải nối model mới, khóa weights/preprocessing/config/runtime bằngfreeze_submission.py rồi chạyFROZEN. Không dùng modelV606 cũ như thể tương thích bộnguồn/cost mới. score_private.py chỉ chấm sau khi hoàn tất đủ4nhánh×434SKU-ngày; xuấtlãi vàdoanhthu chênhbaseline.
Testkhép kín không đồng nghĩa retrain ngay:weights khóa, featurehistory thay đổi từng ngày. Champion/challenger online cần protocolriêng: chỉ dùng ngày đã đóng, validationnội bộ quákhứ, lịchretrain và tiêu chíthaychampion định trước. Runtime hiện chưa tựtrain/retrain.
Chỉ táchfolder không tạo blindtest. Custodian phải giữ01/scorer/manager token riêng, modelprocess không quyền đọc những file đó. Khóa trướcseed/thếgiới/cost/rules, không xem kết quảtest để chỉnhsimulator hoặc chọnmodel. Testởđây là đánhgiámôphỏng được côlập; nguồnproxy côngkhai và kỳđã nghiêncứu trước không trởthành holdoutAEONmới hoàn toàn. Đổi seed không xóa thiênlệch nghiêncứu. Chưa chạytestchínhthức trong lầnbuildnày.

## Nguồn bổ trợ được dùng thế nào?
sources_and_build_use.csv ghiURL,vai trò,giới hạn. CaseAEON–IBM hỗtrợ hướng phối hợpđặt hàng/markdown, không gán kết quảNhật choTânPhú. DonorGreenAI cóordered/unsold nhưngđãscale, cóâm vàkhôngbảo toànunits: đã loại khỏi hiệu chuẩn tỷlệhủy; audit vàhash đi kèm. Không lấy tỷ lệ giả để “chứng minh”AI cólợi.
Muốn kếtluận lợi nhuậnthật cần bổ sung: số chuẩn bị/bán/hủy theoSKU-ngày, hóađơnnguyênliệu/giánhập, logtemgiá/phêduyệt, timestampstockout/refill, quy cáchmẻ/côngsuất/hạnsửdụng và thínghiệmgiá cóđối chứng. Dữliệu cónguồnhiện tại chỉ hỗtrợ nghiêncứu độnhạy, không bảo đảmAI thắng.
