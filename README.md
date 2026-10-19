# SmartFresh · Bakery prototype workspace

Bộ khởi tạo local dành cho nhóm phát triển bằng VS Code. Có giao diện replay V9 chạy được, tài liệu thiết kế flow và backlog. Đây là PoC theo bối cảnh AEON Bakery, không phải sản phẩm chính thức của AEON.

## Chạy ngay

1. Cài Python 3.10 trở lên.
2. Giải nén và mở `smartfresh.code-workspace` bằng VS Code.
3. Mở Terminal tại thư mục này, chạy `python app.py` (Windows có thể dùng `py app.py`).
4. Mở http://127.0.0.1:8000 . Không cần pip, Node hoặc API key cho bản replay.
5. Chọn ngày tháng 09/2022, bấm Phát nhanh hoặc +30 phút. Xem M2, M1 và kết quả đến 22:00.

Kiểm tra: `python -m unittest discover -s tests -v`.

## Đã có / chưa có

| Thành phần | Trạng thái |
|---|---|
| Giao diện nền trắng, điểm nhấn magenta, bảng SKU | Đã có bản khởi tạo |
| Đồng hồ mô phỏng, phát nhanh, nhảy 30 phút, reset | Đã có |
| Replay 30 ngày, 8 SKU từ đầu ra V9 gốc | Đã có |
| Kiểm tra bảo toàn tồn, doanh thu và ràng buộc giá | Đã có |
| VS Code workspace, cấu hình chạy debug, GitHub CI | Đã có |
| Nhập CSV mới, model inference, mô phỏng có thể đổi đầu vào | Chưa triển khai |
| Duyệt/điều chỉnh, lưu SQLite, đăng nhập/phân quyền | Chưa triển khai |
| Gọi OpenAI API và chat nhập liệu | Chưa triển khai |
| Repository GitHub | Đã tạo repo riêng Private; chưa mời thành viên |

Replay hiển thị kết quả đã chạy, không chạy LightGBM lại. UI không có nút duyệt giả. Đổi dữ liệu phải thực hiện trong chế độ inference/simulation sau này, không sửa các CSV replay.

## Tài liệu

- `docs/FLOW_VA_THIET_KE.md`: luồng nghiệp vụ, chỉnh mockup, cách tích hợp ChatGPT.
- `docs/BACKLOG.md`: thứ tự build, chia nhóm việc và tiêu chí nghiệm thu.
- `docs/SOURCES.md`: nguồn đã xem, phạm vi kiểm tra và nguồn gốc dữ liệu.
- `reference/run_v9.py`: bản code nguồn đã đối chiếu, giữ làm tài liệu. Không import từ app vì script thực thi huấn luyện ở top-level.

## Làm việc chung qua GitHub

Repository: https://github.com/uyenpham31241020892-gif/smartfresh-bakery-prototype (Private).

```bash
git clone https://github.com/uyenpham31241020892-gif/smartfresh-bakery-prototype.git
cd smartfresh-bakery-prototype
code smartfresh.code-workspace
python app.py
```

Chủ repository thêm thành viên trong Settings → Collaborators bằng GitHub username. Chưa tự mời ai.

Mỗi người clone repo, mở workspace và tạo nhánh: `feature/m2-inference`, `feature/approval`, `feature/demo-engine`, `feature/assistant`. Dùng pull request vào main; mỗi PR cần mô tả thay đổi, cách chạy và ảnh giao diện khi liên quan. Tránh cùng sửa một file UI lớn; tách component khi bắt đầu build đầy đủ.

`.env.example` chỉ là chỗ dành cho cấu hình tương lai. Không commit API key hoặc dữ liệu POS thật. Chưa có license được áp dụng; nhóm thống nhất quyền sử dụng trước khi công khai.
