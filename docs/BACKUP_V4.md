# Backup và khôi phục dữ liệu ca (offline)

Snapshot ở Model Registry bảo vệ bản sao model V4, khác backup toàn bộ sổ ca/tài khoản.

Dừng server trước, rồi chạy trong thư mục app bằng Python đã cài thư viện:

```powershell
.venv\Scripts\python.exe scripts\backup_restore.py backup --db runtime\smartfresh_v4.sqlite3 --learning runtime\v4_lifecycle --archive SmartFresh_V4_Backup.zip --server-stopped
```

Tệp đích phải chưa tồn tại. Backup gồm database và snapshot V4, có tài khoản đã băm và lịch sử; không gồm `.env`/API key. Bảo quản cùng dữ liệu nội bộ của nhóm.

Khôi phục vào một thư mục **mới**:

```powershell
.venv\Scripts\python.exe scripts\backup_restore.py restore --archive SmartFresh_V4_Backup.zip --destination restored_v4 --server-stopped
```

Công cụ kiểm hash và SQLite, từ chối model ngoài V4, vô hiệu phiên đăng nhập cũ và dừng các đồng hồ/job. Sau đó có thể chạy app với `SMARTFRESH_DB` trỏ đến `restored_v4\state.sqlite3`, `SMARTFRESH_LEARNING_DIR` trỏ đến `restored_v4\learning`; hoặc do người phụ trách kỹ thuật đặt hai phần đó vào đúng runtime khi server đang dừng. Không ghi đè database đang hoạt động, không nhập database model cũ sang V4.
