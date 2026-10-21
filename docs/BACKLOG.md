# Backlog để nhóm cùng build

> Backlog ban đầu của bản replay. Xem [IMPLEMENTATION_V9.md](IMPLEMENTATION_V9.md) để biết chức năng đã chạy và các mục còn mở.

| Ưu tiên | Nhóm việc | Đầu ra và điều kiện hoàn thành |
|---|---|---|
| P0 | Chốt nghiệp vụ | Chốt ngày mục tiêu M2, giờ chốt kế hoạch, giả định 30% từ 21h, xử lý tồn và từ chối đề xuất vi phạm sàn |
| P0 | Tách engine V9 | Tách feature/inference/policy khỏi script chạy batch. Không import script top-level; giữ output so sánh với replay |
| P0 | Đóng gói model | Bundle model M1/M2, danh sách cột encoder theo thứ tự, residual offsets, empirical response, organic fractions, SKU master, policy manifest, dependency versions và checksum |
| P0 | M2 API | Một input snapshot trả forecast, buffer, baseline, floor, batch, prepared_qty, model/policy version; tái hiện kết quả V9 trên input cố định |
| P0 | M1 API | Tồn + bán 30/60 phút + giờ → phản ứng giá → optimizer; đảm bảo monotonic, cap/floor và đúng mốc 30 phút |
| P0 | Simulator | Đồng hồ backend, seed, hàng đợi event, dừng/chạy/nhảy, xử lý các mốc bị vượt qua; input mới làm thay đổi kết quả có thể tái lập |
| P1 | Giao diện vận hành | Form nhập, import CSV, bảng lỗi từng dòng, detail SKU, tính tổng tự động, trạng thái thiếu dữ liệu và lỗi |
| P1 | Duyệt & áp dụng | SQLite lưu run, proposal, approval, applied_price, transaction; chống áp dụng trùng và phát hiện proposal cũ |
| P1 | Chốt ngày | Sổ giao dịch đối chiếu tồn/doanh thu; đóng phiên; lịch sử ngày trước cho M2; không đưa future/hidden data vào inference |
| P1 | Báo cáo | Baseline/M1/M2/joint cùng seed; phân biệt estimated/observed/simulator-only; revenue, waste, lost sales, stockout |
| P2 | Assistant | OpenAI tool calling, xem trước dữ liệu trích xuất, giải thích từ JSON run; không bịa số; mất mạng vẫn dùng form |
| P2 | SHAP nếu cần | Chạy giải thích thật, ghi model/input và mục tiêu giải thích; không coi SHAP dự đoán là toàn bộ lý do optimizer |

Đề xuất phân công theo mảng, chưa gán người: frontend; inference/model packaging; simulation/data; QA/reporting; assistant/integration. Mỗi mảng tạo issue và PR riêng. Không mời thành viên hoặc gửi thông báo khi chưa có tài khoản chính xác và yêu cầu mời.

## Kiến trúc phát triển tiếp

Đề xuất tách frontend React/TypeScript, backend Python/FastAPI và SQLite khi bắt đầu triển khai đầy đủ. Bản starter cố ý dùng Python standard library + HTML để nhóm mở được ngay; chưa cài các dependency trên. Frontend gọi backend; backend giữ đồng hồ, thực thi model/optimizer và lưu nhật ký; assistant chỉ gọi các hàm có schema rõ.

## Nghiệm thu trước buổi trình bày

1. M2 input mới tái hiện đúng batch/sàn; chứng minh forecast và prepared_qty khác nhau.
2. M1 nhận tồn mới, chỉ ra thay đổi đề xuất nếu model/policy thực sự chọn khác; không ép mọi thay đổi input phải đổi giá.
3. Cùng seed, input và phiên bản cho kết quả lặp lại; đổi mức duyệt tác động các giao dịch về sau trong simulation.
4. Nhảy 19:30 → 22:00 vẫn xử lý đủ các mốc và dừng chờ duyệt theo thiết kế.
5. Không đọc doanh số tương lai khi tính model. Kiểm tra truy cập dữ liệu này bằng test engine.
6. Bán + tồn = chuẩn bị theo giả định không bổ sung trong ngày; nếu thêm sản xuất, phải thêm biến bổ sung và điều chỉnh phương trình.
7. Tổng doanh thu bằng tổng tiền từng giao dịch. Tồn/hủy và lost sales không được trộn.
8. Từ chối, chỉnh, hết hiệu lực và gọi API lỗi đều có trạng thái rõ. Khi OpenAI lỗi, M1/M2 local vẫn chạy được.
9. Replay được ghi nhãn rõ; không giới thiệu là inference realtime hoặc dữ liệu POS AEON.
