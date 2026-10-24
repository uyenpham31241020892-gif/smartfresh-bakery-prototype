# SmartFresh — Giai đoạn 5: Data Quality & Provenance
Nhóm A + B06 · Bản build GD5-v1 · 22/10/2026

## 1. Mở và chạy
Giải nén ZIP vào **thư mục mới**, không ghi đè lên bản duy nhất đang dùng. Mở Start.cmd như trước (Windows, Python 3.12). Các model M1/M2 và dữ liệu demo đã nằm trong source; không cần tải file hay cấu hình Copilot để thử DQ.

Vào **Dữ liệu đầu vào** ở menu trái. Phần đầu mới là **Chất lượng & nguồn dữ liệu**, tiếp theo là **Lịch sử nhập & cách ly**, phía dưới là khu vực tải dữ liệu cũ. Bộ code là full source gọn; không đóng gói .venv của máy khác. Start.cmd sẽ tạo môi trường/cài dependencies nếu cần.

Nếu muốn kiểm thử bằng terminal: `python -m pip install -r requirements-dev.txt`, sau đó `python -m pytest -q`.

## 2. Tại sao cần giai đoạn này?
M2 có thể tính ra một con số đẹp từ đầu vào sai thời điểm. Ví dụ: lúc 06:00 ngày 16/08, dự báo thời tiết chỉ phát hành lúc 07:00 thì nhân viên chưa thể biết nó. Dùng nó để dự báo lúc 06:00 là nhìn tương lai. Tương tự, số bán/hàng hủy cuối ngày hoặc hidden demand của simulator không phải đầu vào hợp lệ cho dự báo đầu ngày.

GD5 đặt một cổng kiểm tra **trước khi gọi model M2**, và kiểm tra độ mới luồng bán trước khi tạo gợi ý M1. Lỗi cứng chặn thao tác; cảnh báo cho phép tiếp tục demo nhưng hiển thị rõ hạn chế.

## 3. Ba trạng thái cần hiểu
- **PASS:** vượt các kiểm tra local và timestamp đã khai báo. Không có nghĩa tệp đã được AEON/JMA xác thực, không có nghĩa accuracy đạt 100%.
- **WARN:** cho phép demo nhưng metadata chưa đầy đủ, lịch sử ngắn/thiếu ngày hoặc forecast V9 chỉ có giả định previous_day1.
- **BLOCK / BLOCKED / QUARANTINED:** không cho đầu vào lỗi tạo ca dự báo; không cho file lỗi xác nhận. BLOCKED là xác nhận không thành công ở cổng inference; QUARANTINED là tệp lỗi cấu trúc/dòng/thời gian/cột bị cấm. Không có việc lấy các dòng tốt của file lỗi rồi âm thầm chạy AI.

Ca cũ tạo trước GD5 có nhãn LEGACY, chưa được audit hồi tố. Tạo ca mới để có snapshot GD5. Với ca mô phỏng, đồng hồ tham chiếu là ngày/giờ của ca, không phải thời gian máy tính năm 2026. Vì vậy demo năm 2022 không bị chặn chỉ vì đã cũ so với hôm nay.

## 4. Độ mới lịch sử bán hàng (Nhóm A)
Với mỗi SKU, bảng mới cho biết ngày lịch sử gần nhất, khoảng cách đến ngày dự báo, số ngày thiếu trong 7 ngày trước và trạng thái. Mục tiêu là bắt trường hợp dữ liệu 7 SKU còn mới nhưng 1 SKU đã ngừng cập nhật.

Chính sách GD5-v1: khoảng cách tối đa 2 ngày. Thiếu toàn bộ SKU hoặc quá 2 ngày thì chặn tạo kế hoạch; thiếu một số ngày trong cửa sổ 7 ngày thì WARN, model vẫn có cơ chế dự phòng đã có. Đây là ngưỡng demo, cần khảo sát SLA POS trước pilot.

Ví dụ ca 16/08: lịch sử mới nhất 15/08 là cách 1 ngày; mới nhất 12/08 là cách 4 ngày và bị chặn. Lịch sử cùng ngày 16/08 hoặc tương lai cũng bị chặn. Backend không tự xóa hàng tương lai rồi báo hợp lệ.

## 5. Forecast đúng thời điểm (B06)
Thời điểm dự báo M2 mặc định: **06:00, Asia/Ho_Chi_Minh (+07:00), ngày mục tiêu**. Đây là mốc quyết định mô phỏng, không phải thời gian thực bạn bấm nút.

Ba trường khác nhau:
- `date`: ngày dự báo áp dụng.
- `issued_at`: lúc nhà cung cấp khai báo phát hành forecast.
- `available_at`: lúc nguồn khai báo dữ liệu đã sẵn có cho hệ thống. Nếu forecast không có available_at, prototype dùng issued_at làm giả định sẵn có; không xác thực ingestion thực tế bên ngoài.

Forecast upload phải có issued_at với múi giờ, issued_at và available_at đều không sau cutoff; available_at không trước issued_at. Forecast quá **48 giờ** tại cutoff bị chặn. Mốc đúng 06:00 được chấp nhận. Dấu Z/UTC được đổi đúng trước khi so sánh, không so chuỗi giờ.

Chỉ ghi tên JMA_GSM_PREVIOUS_DAY1 trong file không được phép vượt qua kiểm tra timestamp nữa. Nguồn có tên ERA5/reanalysis/retrospective/evaluation hoặc cột ERA5 bị chặn khỏi inference. Bộ forecast demo V9 tích hợp sẵn được dùng với WARN do chưa có timestamp phát hành từng giờ; không gán timestamp giả để đổi thành PASS.

Lịch sử bán có thể thêm available_at trên mỗi dòng. Nếu khai báo sau cutoff, dòng bị lỗi. Khi toàn bộ lịch sử có timestamp hợp lệ, nguồn ghi `declared_timestamps`; nếu thiếu, ghi `date_only_unverified` và WARN. Timestamp là khai báo, chưa phải chứng cứ được xác thực độc lập.

## 6. Provenance — lần ngược về nguồn
Khi tải tệp, có ô **Nguồn dữ liệu khai báo**: ví dụ “CSV xuất từ quầy A”, hoặc “Synthetic để thử”. Hệ thống giữ tên file, ngày mục tiêu, thời gian nhận, SHA-256, import ID, trạng thái, lỗi và ca đã tạo.

SHA-256 là dấu vân tay nội dung: đổi một ô sẽ đổi dấu vân tay. Nó giúp nhận diện nội dung, **không chứng minh ai tạo file hay file có thật sự từ POS**.

Với ca dự báo, bảng nguồn tách riêng nguồn lịch sử và nguồn thời tiết. Nếu upload chỉ lịch sử nhưng dùng weather demo, giao diện vẫn ghi rõ phần weather là demo. Các ca đã chốt được dùng để cập nhật lịch sử cũng có danh sách ID trong lineage.

## 7. Feature snapshot — dự báo này dùng đúng bộ đầu vào nào?
Mỗi lần lập kế hoạch, backend giữ một snapshot ID dạng SHA-256 gắn với:
- Ngày và mốc quyết định, chính sách GD5.
- Lịch sử đã nhìn thấy, kết quả các ngày trước, weather và provenance.
- Đặc trưng cụ thể đưa vào M2.
- Phiên bản model và hash model, seed nếu mô phỏng, ID ca trước/import liên quan.

Cùng nội dung và lineage cho cùng ID, dù thời gian bấm chạy khác nhau; recorded_at giữ riêng. Thay một số bán hay nguồn sẽ đổi ID. Snapshot không phải mã accuracy; nó giúp trả lời “vì sao hai lần chạy khác nhau?” và tái lập điều tra.

M1 cũng ghi feature_snapshot_id cho đề xuất có dữ liệu hợp lệ, gắn với snapshot M2, đồng hồ ca, giao dịch/tồn kho và model. Kết quả duyệt/áp dụng vẫn giữ trong quyết định như các giai đoạn trước.

## 8. Lịch sử nhập & cách ly
Khu vực mới hiển thị tối đa 100 lượt mới nhất, có nút tải lại. Mở từng lượt để xem nguồn, hash, thời gian, lỗi dòng, warning và ca đã tạo. Cơ sở dữ liệu SQLite giữ các lượt sau khi khởi động lại. Lượt cũ vẫn còn trong DB dù nằm ngoài 100 mục giao diện.

Luồng: upload → preview → kiểm tra → xác nhận → tạo kế hoạch / ghi giao dịch. Tệp hợp lệ vẫn chưa áp dụng nếu chưa bấm xác nhận. Tệp lỗi được lưu như một bản nhập cách ly; không đưa vào ca. ZIP/Excel hỏng cũng được ghi trạng thái từ chối khi parser bắt được lỗi. Giới hạn upload vẫn 20 MB, không phải nơi upload cả source code.

File đúng cấu trúc nhưng lịch sử quá cũ có thể vượt preview và bị BLOCKED tại lúc xác nhận; lỗi đó được ghi vào lịch sử nhập, không tạo ca mới. Khi lỗi, sửa nguồn và upload lại. Import ID mới có dấu vết riêng; không sửa âm thầm bản nhập cũ.

Xác nhận lại cùng import ID không nhập thêm lần nữa. Tệp giao dịch cùng hash đã xác nhận trong cùng ca bị chặn khi upload lại. Việc xác thực nguồn và chống giả mạo nhiều người dùng vẫn chưa phải chức năng production của prototype local.

## 9. Dữ liệu bán hàng M1 còn mới không?
Với ca live, nguồn bán phải có dữ liệu/kiểm tra không quá **30 phút** so với đồng hồ ca. Quá ngưỡng thì không tạo dòng đề xuất M1; người quản lý không thể duyệt đề xuất trống.

Nếu không phát sinh bán mới thật, sau khi kiểm tra, nhấn **Đã kiểm tra: không có bán mới đến phút hiện tại** trong Dữ liệu đầu vào, nhập lý do. Hoặc dùng nút tương tự ở màn M1. Nó ghi một mốc kiểm tra và audit, không xóa giao dịch cũ và không tự sinh bán hàng. Nếu có bán mới, phải nhập giao dịch đúng phút như luồng cũ.

Ví dụ xác nhận lúc 19:30: đến 20:00 vẫn vừa trong 30 phút; sau đó cần dữ liệu/kiểm tra mới. Đây là xác nhận thủ công local; chưa phải heartbeat POS tự động. Trong simulation, luồng có nhãn DEMO và chạy theo đồng hồ mô phỏng.

## 10. Thử 7 tình huống có sẵn
Trong thư mục `examples/gd5`, chọn ngày mục tiêu **16/08/2022** và tải lần lượt:
1. `01_valid_synthetic.xlsx`: đủ lịch sử và forecast có timestamp khai báo → xác nhận tạo ca live, bảng DQ PASS. Nguồn vẫn synthetic.
2. `02_forecast_late.csv`: forecast 07:00 → cách ly.
3. `03_forecast_stale.csv`: forecast quá 48 giờ → cách ly.
4. `04_available_late.csv`: phát hành trước nhưng chỉ sẵn có 07:00 → cách ly.
5. `05_hidden_target_leakage.csv`: cột hidden_demand → cách ly.
6. `06_future_history.csv`: lịch sử chứa ngày mục tiêu → cách ly.
7. `07_stale_history.csv`: preview có warning từng SKU → xác nhận bị chặn vì dữ liệu quá cũ.

Toàn bộ timestamp trong examples là dữ liệu test tự khai báo; không được dùng làm chứng cứ dữ liệu thật.

## 11. Kiểm thử và giới hạn
Bộ kiểm thử tự động: 91 PASS (70 bài sẵn có + 21 trường hợp GD5). Một fixture test learning được thêm timestamp forecast để đáp ứng hợp đồng mới. Các test GD4 duyệt/áp dụng, kế toán tồn kho, học/promotion và API vẫn pass.
7 tệp ví dụ đã gọi API thật qua TestClient: 1 tạo dự báo thành công, 6 bị chặn như dự kiến. Kiểm tra DOM chạy 7 màn hình, 8 dòng SKU, không có lỗi JavaScript. Không có kiểm tra hiển thị bằng trình duyệt đồ họa hoàn chỉnh vì tải bộ cài Chromium thất bại trong môi trường thực thi; DOM check không thay thế visual QA. Có kết quả mẫu tại docs/GD5_SAMPLE_RESULTS.json.

Những gì GD5 chưa làm: kết nối POS/JMA/BigQuery thật, xác thực chữ ký nhà cung cấp, timestamp ingestion từ connector thật, điều chỉnh cutoff/SLA qua UI, phân quyền production, tái kiểm toán toàn bộ lịch sử huấn luyện/holdout, hoặc chứng nhận không thể leakage dưới mọi cách sửa code. Cổng chặn tập trung vào nhập dữ liệu và ca inference local. Dữ liệu training/evaluation cũ vẫn giữ nguyên, không được tự coi là kiểm định mới.

Bản build giữ model, ladder giá, dữ liệu demo và workflow duyệt cũ; không triển khai áp giá AEON. Các ngưỡng 06:00/48h/2 ngày/30 phút hiện nằm trong services/quality.py, cần thống nhất nghiệp vụ trước khi đổi.

## 12. File thay đổi
- services/quality.py: chính sách, kiểm tra point-in-time, freshness, snapshot và M1 feed status.
- services/ingestion.py: kiểm tra cột leakage trước/sau mapping, timestamp và metadata preview.
- services/workflow.py: chặn trước M2, lưu snapshot, truy vết ca, gate độ mới M1 và xác nhận không có bán mới.
- app.py: API quality/import history, ghi lịch sử nhập lỗi, lineage và confirm status.
- web/quality.js + app.js/index.html/simulation.js: dashboard DQ, lịch sử và nhãn vận hành.
- tests/test_quality_gd5.py, fixture tests/test_learning.py; examples/gd5; tài liệu này.
