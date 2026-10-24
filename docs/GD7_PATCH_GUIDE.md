# Dùng PATCH GD7 trên bản GD6 — không tạo lại environment

**Dành cho SmartFresh_GD6_Safety_Incident_Fallback_Full_Source.zip đã bàn giao.**

1. Dừng server cũ (Ctrl+C).
2. Sao lưu thư mục dự án cũ.
3. Giải nén **SmartFresh_GD7_PATCH_Only.zip** ra ngoài.
4. Copy **nội dung bên trong** patch vào đúng thư mục GD6 có **app.py**. Chọn Replace các file trùng và merge thư mục. Không xóa services/web cũ.
5. Giữ nguyên **.venv, .tools, runtime, .env, models, data, requirements và Start-Gemini.cmd**. Patch không có các mục này.
6. Mở lại **Start-Gemini.cmd** cũ; environment được tái sử dụng. Không cần chạy pip hoặc tạo venv mới cho GD7.
7. Ctrl+F5 trình duyệt. Dùng tài khoản GD6 cũ → **Giám sát hệ thống**.

Các bảng monitoring tự thêm vào database cũ; users, session đăng nhập, ca, giao dịch và model không bị thay thế.

Bản FULL dùng khi muốn một source hoàn chỉnh trong thư mục mới, không phải để thay environment đang chạy. Không cần tải cả full và patch nếu chỉ nâng cấp GD6.

Nếu bạn đã tự chỉnh các file nguồn trong GD6, so sánh trước khi chép đè. GD7_PATCH_MANIFEST.json liệt kê checksum trước/sau và các file bổ sung. GD7_FILE_MANIFEST.json là manifest của source đầy đủ phiên bản mới; GD6_FILE_MANIFEST.json cũ nếu còn trong thư mục chỉ là lịch sử, không dùng để kiểm source GD7.

Đọc **docs/GIAI_DOAN_7_HUONG_DAN.md** để thử các tab, ngưỡng và bộ minh họa cô lập.
