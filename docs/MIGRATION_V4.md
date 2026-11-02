# Đối chiếu thay đổi — prototype gốc → V4

Nguồn giao diện và chức năng: `smartfresh-bakery-prototype-Kuyn (1)(1).zip` (391 mục). Nguồn model/dữ liệu: `Data (evaluated)-20261029T043742Z-1-001(4).zip`, nhánh `TRAINED_TESTED`.

| Phần | Xử lý |
|---|---|
| Giao diện/sidebar/tables/biểu đồ/Copilot | Giữ cấu trúc prototype gốc; cập nhật nhãn và cách giải thích theo V4 |
| Auth/RBAC/audit/import preview/quarantine | Giữ cơ chế gốc; mẫu và schema liên quan chuyển V4 |
| M2 | Gọi nguyên `prepare`; nhận đầu ngày/refill đúng output gốc |
| M1 | Gọi nguyên `markdown`; số 0 chuyển thành HOLD trên giá hiện hành; bộ đếm proposal cô lập theo ca |
| Manual/Shadow | Giữ, sửa dropdown và giới hạn theo V4; mọi thay đổi qua duyệt rồi áp dụng |
| Mô phỏng bán hàng | Thị trường Validation V4 giữ phản ứng giá theo giả định gốc qua worker riêng; Replay POS là lựa chọn tách biệt, không nạp thị trường cũ |
| Monitoring | Giữ DQ/accuracy/drift/safety/operations/alerts; reference Fit V4, runtime mới và sandbox tách riêng |
| Reconciliation | Giữ đối soát/xác nhận/hash; công thức chi phí chuyển unit cost V4, phí hủy/markdown |
| Lifecycle | Giữ registry, ghim phiên bản, nhật ký và khôi phục; snapshot cùng V4, không đưa model cũ trở lại |
| Chatbot | Giữ cả ba provider và các công cụ đọc; thay prompt/model context theo V4 |
| CI/health/backup | Giữ chức năng, đổi bộ phụ thuộc và kiểm thử sang V4 |
| `data/current_v9`, `models` cũ, `v606`, `v607` | Không có trong bản phát hành V4, không còn import/đường nạp model cũ |
| Runtime cũ | Không được nhập vào database V4. Bản patch tạo bản sao ngoài thư mục app trước khi thay, không trộn vào dữ liệu mới |

## Chứng minh model không đổi

Các file sau khớp byte với nguồn `TRAINED_TESTED`:

- `v4/smartfresh_adapter.py`: `1e1d14b2bcbb7dd74ee5a74c957e6cf91f7d3e3cdba6d1b8d058e6d180e36237`
- M2: `7de4a8c59229fd1ffe92e96c6b2a4725c9072487cb9562b5c57fb57f4b333e81`
- M1: `df52041c29332619ab9664b6c92dbc7cfe50714bc7fdef3972fbf4b337139c99`

Các tên version lịch sử bên trong policy/artifact được giữ nguyên để bảo toàn hash; tên đối ngoại của model trong app là `SMARTFRESH_V4_LOCKED`. Không train/tune, không có V4.1.

Lớp interface chỉ đổi tên field, trình bày kế hoạch, kiểm input và điều phối trạng thái/duyệt. Các giá trị Q75/Q90 hiển thị cho nhánh quyết định bao gồm kiểm tra thứ tự phân vị **đã có trong adapter**; giá trị raw cũng lưu riêng trong `supply`. Điều này không thay trọng số hoặc hành động V4.

Chi phí đổi giá model: 350đ nguyên bản. Chi phí vận hành demo phân kênh E-ink/tem được ghi riêng; không thay bảng tài chính V4 62 ngày.

## Giới hạn kiểm chứng

API và UI đã kiểm tra theo các bằng chứng QA kèm gói. Kết nối LLM thực tế, POS/E-ink thật và chạy CMD trực tiếp trên Windows chưa được thử trong môi trường này. Không dùng kết quả giả lập làm bằng chứng kết nối thật. Mẫu tương tác dùng Validation V4, khác quy trình closed-loop 62 ngày tháng 7–8; lượt đánh giá đó là Post-Test Development Iteration.

Nguồn worker: `customer_events_ALL_PRIVATE.jsonl` trong bộ V4, chỉ lọc đúng các ngày Validation có morning features. Công thức phản ứng giá và token ổn định lấy từ `pos_core.py` của cùng bộ nguồn; strength 0.6 từ `build_config.json`. Không dùng sự kiện test tháng 7–8 cho mô phỏng này. Tách process để hạn chế đường truyền dữ liệu vào model; đây không phải cơ chế sandbox filesystem/production Custodian được chứng nhận.
