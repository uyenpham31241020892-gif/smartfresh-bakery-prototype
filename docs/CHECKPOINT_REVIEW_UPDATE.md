# Cập nhật dừng snapshot
Bắt buộc duyệt lúc 19:30, 20:30, 21:30. Lúc 20:00 và 21:00 vẫn tính đủ 7 SKU, chỉ tự tiếp tục khi đề xuất AI giữ nguyên mọi mức giảm. Có thay đổi thì dừng đủ bảng 7 SKU để duyệt. Không tự áp dụng giá mới. Missing data hoặc Manual vẫn dừng. Snapshot bỏ qua lưu status auto_hold, không có approved_at/applied_at. Model, nguồn khách, dữ liệu và policy chọn giá giữ nguyên.

Áp dụng patch: dừng app, chép đè services/workflow.py, tests và docs cùng release_manifest.json vào thư mục có app.py. Khởi động lại. Không cần cài lại môi trường. Ca đang chờ duyệt cần xử lý lần chờ hiện tại; quy tắc mới áp dụng cho các snapshot phát sinh sau đó. Nên tạo ca mới để kiểm tra.

Kiểm chứng: python tests/test_checkpoint_review.py — 5 tests passed (mandatory HOLD, optional HOLD, changed proposal, manual/missing, hai đường tick/advance). Đây là test điều phối có stub đề xuất; chưa chạy lại toàn bộ model hoặc kiểm thử trình duyệt trong bản vá này.
