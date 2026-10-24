# GD9.3 — Chế độ vận hành dùng chung

## Thay đổi
- Tổng quan, Kế hoạch sản lượng, Giảm giá cuối ngày: bộ chọn Assisted / Manual / Shadow nằm đầu trang, cùng một trạng thái của ca.
- Xóa hẳn ô “Chế độ giá tại trang M1” và nút chuyển hướng ở An toàn & sự cố; giữ Artifact, phân quyền, trung tâm sự cố và diễn tập.
- Thông báo Manual hướng dẫn dùng nút đầu trang. Liên kết An toàn & sự cố chỉ hiện khi có sự cố đang mở.
- Hướng dẫn M1 về giới hạn giá và tạo lại bảng chỉ xuất hiện ở trang giá.

## Cách dùng
1. Đăng nhập Manager, mở một trong ba trang trên.
2. Chọn chế độ khác, nhập lý do ít nhất 3 ký tự.
3. Hệ thống tạm dừng đồng hồ tự động, lưu lý do và cập nhật chế độ chung của ca. Kế hoạch chưa duyệt được tính lại; kế hoạch đã duyệt được giữ nguyên. Bảng giá trong khung giảm giá được làm mới.
4. Chuyển sang trang khác: nút đang chọn phải giống nhau. Kiểm tra lại đề xuất trước khi duyệt.
5. Nếu có sự cố, xử lý ở An toàn & sự cố. Chế độ Assisted vẫn chịu điều kiện phục hồi; chuyển chế độ không bỏ qua kiểm tra quyền hoặc chính sách.

## Cài patch
Dừng server, giải nén PATCH rồi chép đè nội dung vào thư mục đang chứa app.py. Chạy lại launcher cũ và Ctrl+F5 trình duyệt. Không cần cài lại môi trường. Không xóa runtime, .env hay .venv.
Patch tích lũy dùng cho GD9, GD9.1 và GD9.2; bao gồm các sửa giá và sàn sản lượng trước đó.

## Kiểm chứng
Kiểm tra DOM bằng jsdom với API local: mỗi trang có đúng một bộ chọn ở đầu; đổi Manual tại Tổng quan và Assisted tại Kế hoạch sản lượng đồng bộ cả ba trang; ô cũ bị xóa; trung tâm sự cố còn nguyên; không lỗi JS.
Kết quả hồi quy Python/API và E2E: xem GD9_QA_RESULTS.json và GD9_E2E_RESULTS.json. Không phải kiểm thử trình duyệt Windows thủ công hoặc nghiệm thu AEON.
