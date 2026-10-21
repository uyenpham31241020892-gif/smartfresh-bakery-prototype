# Prototype local — nguồn ZIP ngày 20/10/2026

Nguồn chính: V9-20261020T063226Z-1-001.zip, 173 tệp, SHA256 0d23e880e8ed5bebef4ab1a9ba4127da25775000a4e93d06c8c87d95a27279e8.

Đã kiểm kê mọi tệp, đọc CSV/JSON và trích toàn bộ nội dung văn bản, code, PDF, Word, Excel, notebook bằng audit_sources.py và read_bundle.py. Nội dung trùng byte được đọc một lần. source_inventory.json lưu hash, schema, số dòng và đường dẫn; bundle_content.json lưu phần văn bản đã trích. Đã đọc và render mockup 15 trang từ Downloads.

ZIP ngày 18/10 được kiểm tra trước khi có đường dẫn ZIP đúng. Runtime hiện dùng dữ liệu và mô hình đã đối chiếu với ZIP ngày 20/10; không dùng nhu cầu ẩn hoặc model ngày 18/10. Các dữ liệu tải từ Drive trước đó đã được thay bằng byte từ ZIP đúng.

## Thành phần hoạt động

| Thành phần | Cơ chế thực tế |
|---|---|
| M2 | Native LightGBM từ model đóng băng V9; dự báo mới theo lịch sử và forecast đầu vào |
| Lập sản lượng | Dự báo + residual buffer q=0,85; làm tròn mẻ 4; sàn 90% baseline |
| Baseline | Trung bình sold 7 ngày trước × 1,29 × hệ số cuối tuần 1,07; mẻ 4 |
| M1 | Native LightGBM phản ứng giá, blend 35% model + 65% empirical, hiệu chỉnh monotonic |
| Optimizer | Liệt kê lịch giá hợp lệ; tối đa doanh thu dự kiến trừ phạt tồn 2,5% giá gốc; giữ đúng phá hòa từ nguồn |
| Giải thích M2 | TreeSHAP thực qua pred_contrib; đơn vị bánh |
| Giải thích M1 | Lịch giá, doanh thu và tồn dự kiến của optimizer; không gán thành SHAP giảm giá |
| Copilot | OpenAI Responses API; công cụ chỉ đọc dữ liệu và bằng chứng; không có tool duyệt/áp dụng |
| Upload | CSV, XLSX nhiều sheet, ZIP dữ liệu; preview, kiểm tra từng dòng, hash và xác nhận |
| Ánh xạ cột | Alias định sẵn; GPT có thể đề nghị ánh xạ khi có key; vẫn phải qua validation/preview |
| Giao dịch | Lưu số lượng, giá có hiệu lực, giảm giá và thành tiền từng dòng |
| Lưu trữ | SQLite WAL: phiên vận hành, bản nhập, audit; đối soát trước commit |

Model gốc là **artifact đã huấn luyện sẵn được cung cấp trong V9**. Luồng **Học từ dữ liệu** bổ sung huấn luyện LightGBM thật từ kết quả mới, kiểm tra theo thời gian và xác nhận trước khi thay active model; xem [ADAPTIVE_LEARNING.md](ADAPTIVE_LEARNING.md). Không tự train từ mọi file hoặc dùng dữ liệu demo thay model thật. Hash của cả hai joblib và runtime.joblib gốc được kiểm tra với MODEL_FREEZE trước khi xuất sang native LightGBM. Runtime web không deserialize joblib hoặc thực thi code từ file upload.

GPT chưa được fine-tune trên dữ liệu bakery. Nó được hướng dẫn vai trò và gọi công cụ đọc kết quả model. Chỉ gọi GPT thật khi có API key; thiếu key/lỗi API trả trạng thái rõ ràng, không thay bằng câu trả lời giả.

## Trạng thái và xác nhận

plan_pending → plan_approved → running → price_pending → price_approved → running → close_pending → closed.

Sau khi duyệt kế hoạch, cần xác nhận **đã chuẩn bị** để tạo tồn đầu ngày. Sau khi duyệt giá, cần **áp dụng giá** để đổi giá giao dịch tiếp theo. Điều chỉnh tại bước duyệt phải có lý do và tuân thủ ràng buộc.

M1 chạy 19:30, 20:00, 20:30, 21:00, 21:30. Nhảy tới 22:00 vẫn dừng ở mốc chưa xử lý đầu tiên. Không đổi thời gian khi chờ duyệt/áp dụng. Từ chối giá giữ giá cũ nếu còn hợp lệ; từ 21:00 không thể giữ giá vi phạm sàn.

Mỗi thao tác dùng revision và idempotency key. Giao dịch mới khi chờ duyệt làm hết hiệu lực proposal cũ và chạy lại M1. Áp dụng trùng không ghi lại giá/audit. Xác nhận bản nhập lặp trả đúng ca đã tạo.

Lưu snapshot lịch sử đầu vào, forecast, input hash, model hash, feature values và output theo run. Chỉ ngày đã đóng mới phát hành vào lịch sử ngày sau; feature chỉ lấy ngày trước ngày mục tiêu. Doanh thu là tổng tiền giao dịch, không nhân toàn bộ sold với giá hiện tại.

## Mô phỏng và dữ liệu nhập

- **Mô phỏng tương tác:** sinh lượt mua mới có seed từ trung bình và phân bố cuối ngày khóa từ train. Ban ngày dùng Beta(2,4; 1,8), số lượt Poisson. Cùng ngày/seed sinh cùng sự kiện. Đây là phần mở rộng prototype, không phải observations gốc V9 hay một tập đánh giá độc lập.
- **Dữ liệu nhập:** lịch sử/forecast người dùng tải lên; không tự sinh doanh số. Nhập giao dịch đúng phút hiện tại, giá do backend xác định. Lost sales không tự suy ra từ POS.
- **Đối chiếu V9:** output tháng 9 của run d8b621a5bff64203a32d79ed790dadd2, không gán vào ca đang chạy.

Ngày ngoài 16/08–30/09/2022 cần lịch sử và forecast có issued_at chứa múi giờ, không sau 06:00 ngày lập kế hoạch. Model train trên 2022 chưa được xác nhận chất lượng cho bối cảnh hiện tại. Forecast V9 previous_day1 vẫn có hạn chế timestamp phát hành từng giờ của nguồn.

## Đối soát và kiểm tra

- Inference so với các hàm policy gốc: nhiều mức lịch sử, 8 SKU, 5 slot, tồn 0/3/18/55 và ràng buộc monotonic/cap/floor.
- Tổng TreeSHAP khớp dự báo; thêm lịch sử hiện tại/tương lai không đổi dự báo.
- 480 SKU-ngày baseline/selected: prepared = sold + waste, giao dịch = sold, ledger = revenue, tổng tiền/chi phí/contribution khớp summary.
- WAPE tính lại từ base arrivals đã bán + lost_regular và M2_FORECASTS: **11,953181%**, MAE **3,341412**. Workbook WAPE 12,077197% thuộc hash/source khác.
- Toàn vòng ngày, stale revision, proposal bị thay, chặn ghi lùi giờ và chống xác nhận trùng.
- CSV/XLSX/ZIP, dữ liệu tương lai/trùng/âm, timestamp weather, archive hỏng, ngày mới năm 2026 và inference thật sau import.
- Edge desktop/mobile: upload, M2, M1, duyệt/áp dụng, giao dịch, báo cáo, audit và điều hướng; không phát hiện lỗi JavaScript.

Test tool loop OpenAI dùng stub kiểm tra giao thức, không được coi là gọi API thật. Lệnh kiểm tra trong README.

## Giới hạn còn mở

1. Không có observations gốc đúng hash 9edb47713bab… trong ZIP. Chưa thể tái lập độc lập toàn thí nghiệm tháng 9 với đúng arrival gốc. Ledger thiếu lượt không mua nên không thay thế được.
2. Chưa đủ mã/lineage chứng nhận tái huấn luyện end-to-end M1/M2. Dùng đúng artifact đã huấn luyện, đóng băng, kiểm hash; không dùng M1_Policy_Label_Train để giả thành bài toán response regression.
3. Chưa có API key kiểm thử OpenAI thật. Nhập key ở Cài đặt AI hoặc cấu hình .env.
4. Giá vốn 45%, strength 0,6, mẻ 4 và sàn giảm 30% từ 21:00 là giả định nghiên cứu. Contribution chưa trừ overhead, nhân sự, phần mềm và chi phí triển khai của workbook tài chính.
5. Ứng dụng local một không gian làm việc, chưa có tài khoản/phân quyền và chưa kết nối POS production.

## Tài liệu tích hợp

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
- [OpenAI Function Calling](https://developers.openai.com/api/docs/guides/function-calling)

Model ngôn ngữ nhận dữ liệu qua công cụ và ánh xạ cột qua JSON schema. Backend kiểm tra nghiệp vụ trước mọi thay đổi.
