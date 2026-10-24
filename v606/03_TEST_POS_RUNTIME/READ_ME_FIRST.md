# SmartFresh V6.06 — Dùng bộ nào để train, test và đối chiếu?

## 1. Bản này đã đổi những gì?

Đây là bản nghiên cứu thống nhất 7 SKU với giá khảo sát AEON Tân Phú do người dùng cung cấp. Giá gốc không làm tròn lại: 29.400 / 25.000 / 25.000 / 25.000 / 24.500 / 27.400 / 27.400 VND. Chỉ 5 món có giá giảm khi ế được báo cáo: ba Danish 20.000, croissant 20.000, crepe 23.000. Danish trái cây nhiệt đới và red velvet chưa có giá giảm cụ thể; baseline kịch bản giữ giá hai món này. Không suy ra “ít giảm” thành cấm giảm tuyệt đối.

Giá không còn là ước lượng VND, nhưng nguồn giá là khảo sát người dùng, chưa có ngày đi khảo sát/barcode/hóa đơn để kiểm chứng độc lập. Ngày tiếp nhận 23/10/2026 không phải ngày khảo sát. Giá hiện tại được áp lên kịch bản lịch năm 2022 để so chính sách, không phải giá AEON đã bán trong năm 2022.

**Giá thật do người dùng báo cáo không làm cho số bán, tồn kho và khách mô phỏng trở thành POS AEON thật.** Bản này là thí nghiệm mô phỏng, chưa đủ cơ sở triển khai quyết định thực tại cửa hàng.

## 2. Bốn thư mục, quyền dùng khác nhau

| Thư mục / ZIP cùng tên | Dùng để làm gì | Có đưa cho model không? |
|---|---|---|
| 01_ORIGINAL_BASELINE_PRIVATE | Nguồn nguyên bản, lineage, thế giới khách ẩn, baseline phát triển, bộ chấm riêng | **Không**. Chỉ người quản lý thí nghiệm/custodian giữ |
| 02_TRAIN_VALIDATION | Fit M1/M2 trên fit, chọn cấu hình trên validation | **Có**, theo feature contract và vai trò feature/label |
| 03_TEST_POS_RUNTIME | Master 7 món, lịch, lịch sử đến 30/6, POS server, adapter mẫu, khóa submission | Model chỉ nhận dữ liệu công khai và API **đúng nhánh, đúng thời điểm** |
| 04_GUIDE_DICTIONARY_SOURCES | Hướng dẫn, bảng giá khảo sát, data dictionary, nguồn, phương pháp và kiểm tra chất lượng | Được đọc hướng dẫn; không phải bảng feature để nối vô tội vạ |

Nếu giao việc cho một AI/máy train riêng: **chỉ gửi ZIP 02**, không gửi 01. Khi chạy test, custodian chạy server có quyền đọc 01; agent/model chỉ dùng token nhánh qua HTTP. Không upload tất cả ZIP vào cùng phiên AI rồi gọi đó là test mù. Nếu cần mở POS trên máy local, giải nén 01 và 03 thành hai thư mục ngang hàng; giữ 01 ngoài tài khoản/container của agent.

## 3. Split theo thời gian

| Phần | Khoảng thời gian | Ngày có nguồn | Số SKU-ngày |
|---|---|---:|---:|
| fit | 02/01–30/04/2022 | 111 | 777 |
| validation | 01/05–30/06/2022 | 60 | 420 |
| test | 01/07–31/08/2022 | 62 | 434 |

Tổng 233 ngày có quan sát trong nguồn, không kéo dài thêm ngày, không điền 9 ngày khuyết thành 0 bán. Warm-up tháng 12/2021 lấy trong phạm vi lịch sử proxy gốc, gắn nhãn giả định phân bổ; không phải một tháng AEON được khảo sát bổ sung. Lịch sử đầu test chỉ đến 30/6.

Tết/cận Tết có trong fit nhưng **không có trong validation hay test cuối kỳ này**. Không được báo cáo đã chứng minh khả năng tổng quát hóa Tết. Có cờ OOD và fallback, không chuyển dữ liệu tương lai về fit hoặc xáo trộn ngày để che thiếu coverage.

## 4. Train M2 như thế nào?

Trong `02/fit`, dùng `m2_morning_features.csv` làm X theo cột cho phép trong `feature_contract.json`. Ghép `m2_censor_aware_targets.csv` theo date + sku_code, chọn **một target_horizon** (day/to_1930/to_2130) để không nhân dòng ngoài ý muốn. Bảng target có nhãn bán phục vụ tối thiểu và cờ right-censored; nếu censored=1, không coi sold là nhu cầu đầy đủ, không tự điền upper bound còn trống bằng 0.

`baseline_daily_OBSERVED.csv`, `observed_15min.csv`, `simulated_POS.csv` là lịch sử quan sát mô phỏng. Chỉ dựng lag/rolling từ những bản ghi có available_at/observed_at trước lúc dự báo. Không dùng bán/hủy/doanh thu cuối ngày làm feature buổi sáng cùng ngày. Không lấy bốn biến M1 lúc 20h cho M2 quyết định 6h.

Chọn mô hình bằng `02/validation` có cùng schema, không fit scaler/encoder/imputer bằng dữ liệu tương lai. Sau khi chọn có thể refit trên fit+validation và khóa lại; không dùng tháng 7–8 để chọn mô hình hoặc chỉnh simulator. `model_io_guard.py` có loader allowlist để giảm nhầm lẫn. Mô hình V4/V6.03/V6.04 cũ không được coi là tương thích với 7 mã mới.

## 5. Train M1 như thế nào?

X: `m1_checkpoint_features.csv`. Có đủ prepared_qty, inventory_at_decision, sold_last_30min, sold_last_60min, cộng tồn quầy/kho, giá giảm hiện hành và sàn đã công bố. Hành động: `m1_logged_actions_TREATMENT_ONLY.csv`. Kết quả sau hành động: `m1_outcomes_LABELS_ONLY.csv`. Ghép date + sku_code + time; outcome chỉ khả dụng sau 30 phút, tuyệt đối không đưa outcome hoặc hành động đã ghi nhận vào X trước quyết định.

Baseline không giảm trước 21h, nên TRAIN vẫn không có đối chứng đáng tin để học tác động nhân quả giảm sớm. M1 có thể học dự báo bán/thu dưới hành động ghi nhận, hoặc học bắt chước policy; chưa thể chứng minh uplift từ giá chưa thử. HOLD là hành động hợp lệ. Default mô phỏng không sinh thêm khách do giảm giá; không gán độ co giãn tự nghĩ thành bằng chứng từ khảo sát. Muốn kiểm tra các giả thuyết giá, phải chốt kịch bản nhạy cảm trước đánh giá và báo cáo là ASSUMED.

## 6. “Tập gốc để so doanh thu” là cái nào?

Có hai nghĩa cần phân biệt:

- `01/french_source_original_UNMODIFIED.csv`: nguồn French Bakery nguyên bản 234.005 dòng, đơn giá euro của cửa hàng nguồn. Không dùng tổng tiền euro này làm doanh thu AEON đối chứng.
- `01/baseline_development_OBSERVED.csv`: baseline mô phỏng 7 món đã tính lại bằng giá khảo sát, kỳ phát triển tháng 1–6. Dùng đối chiếu validation cùng ngày/cùng thế giới khách; bảng này không chứa nhãn lost sales ẩn. `04/baseline_development_revenue_summary.csv` là tổng hợp tham khảo, không phải kết quả test AI.

Doanh thu baseline của kỳ TEST tháng 7–8 **chưa chạy sẵn**. Khi đánh giá chính thức, chạy bốn nhánh BASELINE, M1_ONLY, M2_ONLY, JOINT_M1_M2 trên cùng dòng khách tiềm năng, nhưng từng nhánh có tồn kho, giá, refill và lịch sử riêng. So doanh thu AI và BASELINE của **cùng kỳ chạy**, không so doanh thu tháng 7 với tổng tháng 1–6 và không replay cố định số bán baseline cho AI.

Kết thúc chạy, `code/score_private.py --scorer-dir <thư mục kết quả>` tạo `BUSINESS_KPI_COMPARISON_SCORER_ONLY.csv/json`: doanh thu từng nhánh, chênh lệch VND/% với baseline, hủy giả định, lost sales mô phỏng, tỷ lệ đáp ứng lượt yêu cầu, còn hàng lúc 21:30 và stockout trước 21:30. Mặc định bộ chấm từ chối nếu chưa đủ 434 SKU-ngày x 4 nhánh. `--allow-partial-demo` chỉ dành cho phát triển.

Chi phí sản xuất/hủy chưa có khảo sát: để trống, không lấy 45% giá bán hay 1.000đ làm “chi phí thật”. Do đó cột lãi góp để thiếu; so doanh thu chưa chứng minh tăng lợi nhuận. Hủy cuối ngày và hạn dùng một ngày cũng là giả định cần kiểm chứng, nhất là crepe/red velvet có thể có quy trình giao hàng, hạn dùng khác bánh nướng tại quầy.

## 7. Mở POS trên Windows, không cần máy POS thật

1. Cài Python 3.10 trở lên. Runtime dùng thư viện chuẩn, không cần LightGBM để mở bàn thử.
2. Giải nén ZIP 01 và 03, bảo đảm chúng là hai thư mục ngang hàng với đúng tên trên.
3. Trong 03, chạy `RUN_POS_DEMO_WINDOWS.bat`.
4. Giữ cửa sổ terminal mở; lấy **MANAGER TOKEN**, mở `http://127.0.0.1:8765`, dán token và bấm Kết nối.
5. DEMO chỉ dùng ngày **15/06/2022 trong validation**, không mở tháng 7–8. Màn hình có 7 món và giá khảo sát.
6. Bấm mở ngày, tiến 15 phút hoặc tới 20:00. Nhập kế hoạch trước mở cửa; dùng ô “giá thu VND” để đề xuất 20.000 hoặc 23.000 thay vì ép tỷ lệ tròn 20%. Chờ duyệt không đổi giá; bị từ chối giữ giá; được duyệt và tới giờ hiệu lực thì thẻ giá và giao dịch mới dùng đúng giá được duyệt. Hóa đơn trước đó không bị sửa.
7. M1 có thể giữ giá; không bắt buộc giảm lúc 19:30–21:00. Baseline chỉ xét giảm sau 21h nếu pace bán dự kiến chưa tiêu thụ hết lượng dư theo heuristic đã khai báo. Mặt hàng bán nhanh có thể giữ nguyên giá dù tồn nhiều. Tem đã chọn giữ tới cuối ngày. Đây là kịch bản, không phải log policy AEON đã đo.
8. Kết thúc ngày: server cộng doanh thu, số bán, lượng còn; cập nhật lịch sử riêng từng nhánh. Kế hoạch ngày sau lấy từ M2 đọc lịch sử nhánh đó. Dữ liệu test không đặt sẵn lượng chuẩn bị tương lai cho AI. Lượng chuẩn bị ngày mới là bánh/món mới cung ứng; không tự mang bánh đã hết hạn hôm trước sang.

POS không phải model: DEMO dùng placeholder kế hoạch và đề xuất thủ công. `model_adapter_TEMPLATE.py` cố ý chưa có model. Sau khi train, nối M2 vào `prepare(...)`, M1 vào `markdown(...)`; bridge gọi model bằng context quan sát đúng thời điểm. Quản lý/token quản lý riêng mới duyệt giá.

## 8. Chạy test chính thức

Custodian giữ 01, chạy server; model chạy bằng tài khoản/container khác, không mount 01, không thấy file kết quả chấm và không có token quản lý. Dù API có kiểm tra token, nó không ngăn được code model đọc file nếu bạn đặt tất cả trong cùng filesystem có quyền truy cập.

Khóa model, adapter, feature contract, runtime và policy trước khi chạy bằng `freeze_submission.py`. Giá trị market SHA256 công khai nằm ở `03/TEST_market_commitment.csv`, không cần gửi file khách ẩn cho model.

Ví dụ terminal tại 03 sau khi có model và adapter hoàn chỉnh:

```text
python code/freeze_submission.py --models-dir PATH_TO_MODELS --adapter PATH_TO_ADAPTER.py --config build_config.json --market-sha256 COPY_SHA256_FROM_COMMITMENT --out submission.json
python code/pos_server.py --runtime-dir . --custodian-dir ../01_ORIGINAL_BASELINE_PRIVATE --mode FROZEN --submission submission.json --scorer-output ../01_ORIGINAL_BASELINE_PRIVATE/official_run_001
```

Sau khi server trả token nhánh, gọi bridge tại mỗi lần cần quyết định, ví dụ:

```text
python code/agent_bridge.py --branch JOINT_M1_M2 --token OWN_BRANCH_TOKEN --adapter PATH_TO_ADAPTER.py --submission submission.json
```

M2 cần gửi kế hoạch trước mở cửa. M1 gửi đề xuất tại checkpoint, quản lý duyệt trước khi server đi tiếp. Bridge hiện làm một bước, không phải scheduler tự động train/chạy trọn kỳ. Custodian hoặc chương trình điều phối cần gọi ba bridge nhánh AI, xử lý duyệt theo quy trình thống nhất rồi advance đồng hồ. Không được cho nhánh AI một chế độ duyệt ưu ái hơn baseline; log mọi lần duyệt/từ chối.

Sau khi đóng đủ kỳ:

```text
python code/score_private.py --scorer-dir ../01_ORIGINAL_BASELINE_PRIVATE/official_run_001
```

Trọng số model giữ cố định trong chế độ FROZEN, nhưng lag/rolling và lịch sử quan sát cập nhật hằng ngày theo từng nhánh. Champion/challenger huấn luyện định kỳ là bước phát triển riêng, chọn bằng validation rồi mở vòng test mới. Không âm thầm retrain bằng kết quả test rồi vẫn gọi là một holdout độc lập. Nếu muốn đánh giá online learning, phải đăng ký trước thuật toán/lịch cập nhật và hạn chế dữ liệu, không dùng nhãn ẩn.

## 9. Data leakage và giới hạn bằng chứng

Model chỉ nhìn POS đã xảy ra, tồn hiện tại, kế hoạch đã biết, lịch và thời tiết ngày trước. Nhu cầu ẩn, khách không mua được, first_unserved, lost sales và lineage test chỉ thuộc 01/bộ chấm. Giá khảo sát là metadata công khai, không phải nhãn nhu cầu tương lai.

Thời tiết là Open-Meteo reanalysis lịch sử ngày trước, **không phải JMA forecast phát hành trước quyết định**. Bản này chưa thay được bằng JMA đúng vintage; không dùng thời tiết thực tế cuối ngày làm feature buổi sáng. Muốn dùng dự báo cùng ngày cần thêm issued_at <= decision_at và đối chiếu vị trí Tân Phú.

Tách thư mục, hash và token hỗ trợ một quy trình test không lộ tương lai cho policy; chúng không biến nguồn proxy công khai/kỳ thời gian từng nghiên cứu thành holdout AEON độc lập chưa ai từng xem. Gọi đúng: **test mô phỏng tách quyền truy cập, khóa trước khi đánh giá**. Muốn holdout mù mới về thực địa cần kỳ POS AEON mới chưa dùng phát triển.

## 10. Dữ liệu được dựng từ đâu?

Giữ nguyên 233 ngày và tổng lượng nhu cầu kịch bản theo ngày/slot đã dựng ở V6.04; không mua thêm hay giả vờ có nguồn public mới trong lần tổng hợp này. Nguồn French Bakery gốc còn nguyên ở 01. Bước V6.04 đã dùng 5 nhóm bánh French, co thời gian sang 08–22h, nhân lượng 2x và phân bổ cao điểm sau 17h, hệ số lễ/Tết/mưa theo giả định. Đây không phải hệ số ước lượng AEON.

Vì không có doanh số bảy món mới, **không giả vờ ánh xạ một-một** baguette/croissant thành Danish/crepe/red velvet. Thay vào đó gom luồng proxy ở cấp cửa hàng rồi phân bổ từng đơn vị bằng SHA256 với tỷ trọng kỳ vọng đều 1/7. Quy tắc cố định, lưu seed/lineage riêng, giữ nguyên tổng từng slot và không dùng kết quả model để chỉnh lại. Đây là giả thuyết trung tính để test kỹ thuật, **không xác nhận tỷ trọng, cấu trúc giỏ hàng hoặc cầu riêng từng SKU AEON**. Nhận xét “đắt khách, ít giảm” được lưu định tính, chưa quy ra hệ số cầu tùy ý.

Do đó có thể dùng bộ này huấn luyện thử và kiểm tra vòng lặp POS/khả năng thi hành giá, nhưng kết quả SKU-aware của AI còn phụ thuộc giả định phân bổ. Không được lấy chúng làm bằng chứng model đã học đúng nhu cầu bảy món ngoài đời. Cần POS thực theo SKU để thay bước này. Phương pháp đầy đủ và các giả định ở `04/BUILD_METHOD.md`; tất cả khác biệt này phải được giữ trong báo cáo.

## 11. Chưa có gì trong bản này?

Không có model đã train, không có kết quả test AI chính thức, không có lợi nhuận thực AEON, không có phản ứng giá nhân quả và không có khảo sát định lượng số bán/tồn/công suất. Không bảo đảm 97% service từ mô phỏng. Không dùng kết quả V4 để báo cáo thành tích cho V6.06.
