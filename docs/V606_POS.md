# Current: V606 service2130 v2

See [current guide](V606_SERVICE2130.md). Original prototype at http://127.0.0.1:8000. Start a NEW session for the changed supply policy; older sessions are preserved. Sections below describe earlier iterations.

# Prototype integration supersedes standalone POS

Use Start.cmd and http://127.0.0.1:8000. See [V606 prototype guide](V606_PROTOTYPE.md). The standalone DEMO below is historical and not the current entrypoint.

# POS V6.06 với model đã train

Chạy `Start.cmd`, mở http://127.0.0.1:8765, nhập MANAGER TOKEN in trong terminal. `app.py` cũng mở luồng này. Không dùng model V9/8 SKU cũ.

1. Bấm **Chạy M1/M2 tại mốc này** lúc 06:00. Xem kế hoạch M2_ONLY và JOINT_M1_M2. OOD dùng fallback đã khai báo, cần quản lý xem xét.
2. Mở ngày, tiến từng 15 phút hoặc tới 20:00 (dừng tại 19:30 để quyết định).
3. Tại 19:30, 20:00, 20:30, 21:00, 21:30, bấm **Chạy M1/M2 tại mốc này**. Duyệt/từ chối các đề xuất rồi tiến giờ. Hàng hết không đề xuất giá; HOLD giữ giá hiện tại.
4. Tới 22:00 là đóng ngày validation 15/06/2022. DEMO không mở tháng 7–8.

Trọng số cố định, không retrain. M1 bắt chước hành động đã ghi nhận, chưa có bằng chứng uplift nhân quả; adapter không giảm sớm trước 21h. M2 dùng target day có kiểm duyệt, không bảo đảm mức phục vụ. Sản lượng làm tròn theo mẻ và giới hạn công suất master công khai, không chuyển tồn hết hạn sang ngày sau. Không dùng outcome regressor để tối ưu giá chưa thử.

Adapter chỉ nạp artifact đã train, contract và sku_master công khai. X chỉ gồm cột allowlist. Lịch sử phải trước ngày dự báo và cùng SKU; thời tiết phải ngày trước. Mỗi bridge chỉ nhận token nhánh, không nhận manager token. ZIP 02/04 không được giải nén làm nguồn feature. Không đọc nội dung khách ẩn để chỉnh policy.

Dữ liệu/model/reference/database cũ đã chuyển ra bản sao lưu ngoài repo; đường dẫn trong `v606/local_config.json` (không commit). ZIP gốc giữ nguyên. Các script/test V9 cũ chỉ là tài liệu lịch sử, không dùng cho runtime mới. Code app cũ lưu ở `docs/legacy_app_v9.py.disabled` để tham khảo.

## Test chính thức FROZEN

DEMO cùng tài khoản Windows chỉ kiểm tra tích hợp. Test tách quyền cần custodian chạy server ở tài khoản/container khác, giữ 01 và kết quả chấm; tài khoản model chỉ có artifact/public runtime/adapter và token nhánh qua HTTP. Tách thư mục không tạo ranh giới quyền truy cập.

Khóa model, adapter, runtime, config, commitment bằng `code/freeze_submission.py` theo READ_ME_FIRST.md trước đánh giá. Đặt submission ngoài cây runtime và giữ bản sao độc lập ở custodian. Giữ đường dẫn artifact tương ứng khi chạy bridge.

Custodian chạy `code/pos_server.py --runtime-dir PUBLIC --custodian-dir PRIVATE --mode FROZEN --submission SUBMISSION --scorer-output NEW_PRIVATE_OUTPUT`. Không truyền `--adapter`; FROZEN không cho endpoint local chạy model ở custodian.

Tài khoản model chạy `code/agent_bridge.py --url SERVER --branch BRANCH --token OWN_TOKEN --adapter ADAPTER --submission SUBMISSION` cho ba nhánh AI trước mở ngày và tại năm checkpoint. Quản lý duyệt theo quy trình đã chốt, sau đó advance. Giữ bốn nhánh và lịch sử riêng; không chỉnh policy sau khi xem test.

Sau đủ 62 ngày, custodian chạy `code/score_private.py --scorer-dir NEW_PRIVATE_OUTPUT`. Phải đủ 434 SKU-ngày × 4 nhánh; không dùng `--allow-partial-demo` cho báo cáo chính thức. Doanh thu mô phỏng không phải lợi nhuận hay kết quả POS AEON thực.
