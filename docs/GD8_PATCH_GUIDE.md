# PATCH GD8 — chỉ áp dụng lên GD7

Dừng server, backup project. Giải nén patch bên ngoài project; chép nội dung vào thư mục chứa app.py, gộp thư mục và Replace file trùng tên. Không xóa thư mục project.

Không cần cài lại môi trường. Giữ nguyên .venv, .tools, .env, runtime, models, data, reference, requirements và launcher. Khởi động lại Start-Gemini.cmd hiện có; Ctrl+F5.

Mã mới bổ sung đối soát, registry, holdout và quản trị model. **F04 được bỏ khỏi giao diện theo yêu cầu.** File output/reference V9 vẫn được giữ nguyên. Nếu bạn tự sửa code sau GD7, cần đối chiếu trước khi ghi đè file trùng tên.

Full source không chứa environment/database cá nhân. Patch giữ database/tài khoản/phiên ca hiện có. Schema mới chỉ thêm bảng, không drop bảng cũ.

GD8_PATCH_MANIFEST.json ghi before/after SHA256 so với ZIP GD7 đã giao; không có file bị xóa. GD8_FILE_MANIFEST.json là manifest source mới. Manifest GD7 còn trong thư mục cũ chỉ là lịch sử.

Hướng dẫn vận hành: docs/GIAI_DOAN_8_HUONG_DAN.md.
