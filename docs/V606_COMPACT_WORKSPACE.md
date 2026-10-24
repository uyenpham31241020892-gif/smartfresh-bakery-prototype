# V6.06 · Workspace theo ca, policy v3

Chạy **Start.cmd**, mở **http://127.0.0.1:8000**, nhấn **Ctrl + F5**. Tạo **Ca mới** ngày 01/07/2022 để dùng kế hoạch giảm đệm. Dữ liệu ca cũ được giữ nguyên; thay policy không được sửa lại giao dịch hay tồn của ca đã chạy.

- Trước 17:00, trang vận hành chính là **Kế hoạch sản lượng**. Từ 17:00, trang chính chuyển sang **Giảm giá cuối ngày**; M1 bắt đầu xét giá tại 19:30. Giao dịch và báo cáo vẫn mở được; các trang kỹ thuật được gom vào mục **Hệ thống & dữ liệu** đang thu gọn.
- **Giữ giá:** ghi quyết định HOLD rồi tiếp tục ca, không cần quản lý duyệt. **Đổi giá:** chỉ những SKU có giá thu thực sự khác giá hiện hành mới cần duyệt; giá chưa đổi cho tới khi quản lý duyệt và áp dụng. Thiếu dữ liệu vẫn bị chặn, không tự coi là HOLD an toàn.
- Đề xuất M2/M1 có phần **Copilot giải thích** tự tải bên cạnh, gắn với snapshot đề xuất. Phần căn cứ số liệu hiện ngay; phân tích LLM tải bất đồng bộ, cache theo đề xuất để tránh gọi lại ở từng lần polling. Nếu AI lỗi, giao diện nêu rõ, không gọi phần tóm tắt theo quy tắc là câu trả lời AI.
- **Chi phí chưa biết:** hiển thị “Chưa có dữ liệu chi phí”, chưa tính biên đóng góp/lợi nhuận. Không thay null bằng 0đ, không dùng tỷ lệ giá vốn 45% cũ. **0 lượt không phục vụ** nghĩa là không có lượt yêu cầu mua bị mất do hết hàng trong khoảng đã mô phỏng; không phải lượng khách hay doanh số bằng 0.

## Điều chỉnh đệm và tính công bằng của phép so sánh

Giữ nguyên 9 tệp artifact trong ZIP Train_Validation_Results. Chỉ sửa lớp policy cung ứng, không retrain. Dùng kỳ vọng tải khách công khai, ảnh hưởng có giới hạn của dự báo gốc, buffer 1,64 × căn bậc hai kỳ vọng và dự trữ 4 chiếc/SKU, làm tròn mẻ 4. Các hệ số và công suất vẫn là giả định phát triển, không phải số đo AEON hoặc bảo đảm mức phục vụ.

Đã tách phiên bản dòng khách khỏi phiên bản policy. Với cùng ngày 01/07/2022, seed 42, giữ nguyên **823 lượt mua**: lượng Joint chuẩn bị giảm từ **1.244 xuống 980**; bán 823, tồn cuối giảm **421 xuống 157**, không mất lượt mua trong lần mô phỏng này. Bốn seed kiểm tra 0, 1, 42, 606 vẫn còn hàng từng SKU tại 21:30. Mẫu kiểm tra không chứng minh SLA hay tối ưu toàn cục. Baseline v3 chuẩn bị 976, tồn cuối 153 và cùng doanh thu với Joint trong seed 42; không có bằng chứng Joint vượt baseline từ kết quả này.

Đây là kịch bản mô phỏng phát triển đã điều chỉnh sau khi xem kết quả trước đó, không phải test holdout mù mới. Không dùng test để fit lại trọng số, không đưa nhãn/khách ẩn hoặc dữ liệu tương lai vào feature hay Copilot.

## Xác minh

`python scripts/verify_v606.py` chạy các kiểm tra V6.06 và ghi bằng chứng theo đúng release. Bao gồm kiểm tra giá HOLD không dừng ca, giá thay đổi chưa áp dụng trước duyệt, chi phí null, snapshot giải thích AI, tồn 21:30 và trình duyệt Edge theo ca sáng/tối. Kiểm tra trình duyệt dùng phản hồi LLM giả lập để tái lập; đường giải thích tự động cũng đã được gọi thử thực với Ollama/qwen3.5:4b.
