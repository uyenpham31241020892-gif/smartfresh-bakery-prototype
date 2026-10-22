# PATCH GD9 — áp dụng lên GD8

Dừng server, backup project. Giải nén patch bên ngoài, copy nội dung vào thư mục chứa app.py, gộp thư mục/Replace file trùng tên. Không xóa project cũ. Giữ .venv, .tools, .env, runtime, models, data, reference, requirements và launcher.

Chạy Start-Gemini.cmd cũ, Ctrl+F5. Không cần tạo lại environment hoặc cài thư viện. Patch thêm cả .github/workflows/ci.yml, scripts, release_manifest.json và bằng chứng QA; cần chép cả thư mục .github.

Không có xóa file. F04 tiếp tục không hiện trên prototype theo yêu cầu. Các chỉnh sửa code riêng sau GD8 cần đối chiếu trước ghi đè. Tài khoản/ca/lịch sử vẫn nằm trong runtime cũ.

GD9_FILE_MANIFEST.json là manifest source mới. Manifest GD8 còn trong project chỉ là lịch sử. GD9_PATCH_MANIFEST.json ghi before/after checksum so với full source GD8 đã gửi.

Hướng dẫn vận hành/backup/CI/GO-NO-GO: docs/GIAI_DOAN_9_HUONG_DAN.md.
