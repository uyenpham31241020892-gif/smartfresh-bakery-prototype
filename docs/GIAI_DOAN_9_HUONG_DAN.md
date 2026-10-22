# SmartFresh — GD9: Final QA & Deployment Readiness

## Phạm vi thực tế

G01–G09 được bổ sung/kiểm thử trên prototype local. G10 BigQuery chưa tích hợp vì chưa có quyền truy cập, project, service account và hợp đồng dữ liệu của AEON. Không có adapter giả và không tạo giao dịch thật. F04 baseline vs M1+M2 tiếp tục không có trong giao diện; file V9 lịch sử giữ nguyên.

Đây là bản sẵn sàng kiểm tra và bàn giao demo local, không phải chứng nhận chạy production AEON. CI được bàn giao bằng file workflow, chưa push hoặc chạy trên repository GitHub của bạn. Các kết quả kèm theo được chạy trong môi trường kiểm thử này với dữ liệu tổng hợp/database tạm.

## Cập nhật từ GD8, không tạo lại environment

Dừng server Ctrl+C; sao lưu project. Giải nén PATCH ngoài project rồi chép nội dung vào thư mục đang chứa app.py, gộp thư mục và thay file trùng tên. Không xóa project cũ. Giữ .venv, .tools, .env, runtime, models, data, reference và các launcher. Patch không thay requirements hoặc launcher, không cần pip install lại.

Khởi động Start-Gemini.cmd hiện có, Ctrl+F5. Nếu bạn tự sửa code sau GD8, đối chiếu file trùng tên trước khi ghi đè. Full source chứa ứng dụng/model/data; không chứa environment hay database/tài khoản/API key riêng của bạn. Dùng patch nếu muốn tiếp tục runtime hiện tại.

## G01 — Health check

GET /api/health hoạt động không cần đăng nhập, chỉ trên host loopback được phép. Kiểm tra:

- SQLite BEGIN IMMEDIATE và quick_check, bảng/cột cốt lõi theo schema contract.
- Model active tải được, checksum artifact đúng; lỗi model hoặc mất artifact trả HTTP 503.
- Các dependency cần thiết có trong môi trường hiện tại, kèm phiên bản đã cài.

HTTP 200 + ok=true nghĩa các kiểm tra trên đạt; không đồng nghĩa đã nghiệm thu nguồn POS, SLA hay provider AI chat. AI giải thích là tùy chọn; health không gọi Gemini/OpenAI hoặc kiểm tra bằng API key. HTTP 503 trả code NOT_READY, ok=false và Request ID, không lộ đường dẫn/API key trong exception.

Dependency chưa import được ở thời điểm khởi động có thể làm server không khởi động; endpoint chỉ chạy sau khi app khởi động thành công. Launcher cũ vẫn kiểm tra môi trường trước khi chạy. Không có cam kết health phát hiện được mọi lỗi phần cứng hoặc hết dung lượng ổ đĩa chỉ từ quick_check.

## G02–G03 — API errors và bảo vệ

Giữ URL API hiện tại; không đổi đồng loạt sang /api/v1. Lỗi JSON có error, code, request_id; X-Request-ID trên response. Validation chỉ trả tên trường/loại lỗi, không echo body chứa mật khẩu. Lỗi không dự kiến trả INTERNAL_ERROR, không trả raw exception; log chỉ ghi loại lỗi và Request ID.

Quyền backend vẫn có hiệu lực khi gọi HTTP trực tiếp: Viewer chỉ đọc; Staff không duyệt giá, thay model, xác nhận đối soát hoặc quản lý sự cố; Manager mới được thực hiện các thao tác đó. Không dùng tên người duyệt gõ tự do thay danh tính đăng nhập.

Giữ cookie HttpOnly, SameSite=Strict và giới hạn loopback. Chặn Origin khác host/scheme và Sec-Fetch-Site=cross-site cho thao tác ghi. Không có Origin vẫn cho phép CLI đã xác thực; đây là thiết kế local, không phải cơ chế SSO/CSRF production. Host ngoài localhost/127.0.0.1/testserver bị chặn.

Request ghi bị giới hạn tổng body 25 MiB cả khi gửi chunked/không có Content-Length. Upload dữ liệu vẫn có giới hạn nghiệp vụ 20 MB riêng. Response thêm no-store cho API, nosniff, frame DENY, no-referrer. Không gọi đây là pentest hoặc bảo đảm chống mọi tấn công. Chưa có TLS/SSO/secret manager của doanh nghiệp; không mở server ra Internet bằng cách bỏ host guard.

## G04 — Request traceability

Mỗi request có ID mới do server tạo, không tin ID do client gửi. Khi gặp lỗi, sao chép X-Request-ID hoặc trường request_id, mở **GO / NO-GO → Truy vết API**.

GET /api/trace/{id} trả telemetry route/method/status/latency, audit liên quan và giao dịch có cùng Request ID. Các giao dịch mới có transaction_id, model_version, feature_snapshot_id và proposal_id gần nhất đã áp dụng. Nếu bán trước khi có quyết định M1, proposal_id=null là đúng; không tạo ID giả.

Giao dịch mô phỏng do clock nền tạo có thể có request_id=null vì không phát sinh từ HTTP. Audit/ledger trước GD9 không được tự gán Request ID. Trace không thu body/query/password/key. Endpoint chỉ dành cho tài khoản đã đăng nhập và đọc dữ liệu local còn lưu.

## G05 — Backup/restore có kiểm chứng

Công cụ CLI: scripts/backup_restore.py, chỉ dùng khi server đã dừng. Không có nút phục hồi trực tiếp ghi đè database đang chạy.

Trong PowerShell tại project, dùng Python của environment đang có (nếu môi trường của bạn ở đường dẫn khác, thay đường dẫn Python):

```powershell
.\.venv\Scripts\python.exe scripts\backup_restore.py backup --db runtime\smartfresh.sqlite3 --learning runtime\learning --archive SmartFresh_backup.zip --server-stopped
```

Nếu có SMARTFRESH_DB hoặc SMARTFRESH_LEARNING_DIR tùy chỉnh, dùng đúng đường dẫn đó. Tên ZIP đích phải chưa tồn tại. Backup dùng SQLite backup API, kiểm tra quick_check, đóng gói database và model học/training snapshot/report, kèm checksum. Không copy .env. Không tự copy model frozen/data/source vì chúng nằm trong full source; giữ bản source tương ứng cùng backup.

Bản backup chứa dữ liệu ca, lịch sử và password hash, nên cần bảo quản nội bộ. Cờ --server-stopped là xác nhận của người vận hành; công cụ không tự chứng minh mọi process đã dừng. Dừng server là cần thiết để database và thư mục model không thay đổi giữa lúc sao lưu.

Diễn tập phục hồi vào thư mục mới:

```powershell
.\.venv\Scripts\python.exe scripts\backup_restore.py restore --archive SmartFresh_backup.zip --destination runtime_restored --server-stopped
```

Công cụ kiểm tra hash, ZIP traversal, tên trùng/kích thước, database và artifact của model active/các ca đã ghim. Chỉ công bố thư mục đích sau khi kiểm tra đạt; không ghi đè runtime cũ. Phục hồi giữ tài khoản/lịch sử, xóa token đăng nhập cũ, tắt simulation clocks, đánh dấu job dở dang là interrupted và ghi audit BACKUP_RESTORED. Người dùng phải đăng nhập lại.

Để dùng bản phục hồi sau khi kiểm tra, giữ runtime gốc làm bản dự phòng. Có thể đặt SMARTFRESH_DB trỏ tới đường dẫn tuyệt đối runtime_restored\state.sqlite3 và SMARTFRESH_LEARNING_DIR trỏ tới runtime_restored\learning trước khi chạy launcher, hoặc chép các phần đã kiểm tra vào runtime theo quy trình bàn giao của nhóm. Không chạy hai server cùng một database. Kiểm tra health, registry và ca đối soát sau khi đổi đường dẫn.

## G06 — GitHub CI

.github/workflows/ci.yml chạy khi push, pull_request hoặc workflow_dispatch. Matrix Ubuntu/Windows, Python 3.12; cài dependencies dự án và pytest; kiểm tra cú pháp JS; chạy scripts/run_qa.py; lưu artifacts JSON/JUnit/release manifest. Workflow chỉ có contents:read, không deploy, không cần provider AI key hoặc dữ liệu AEON.

Để kích hoạt: đưa đầy đủ source/model/data cần thiết và thư mục .github vào repository của nhóm, push rồi xem tab Actions. Không push .env, .venv, runtime hoặc backup. Bản ZIP chứa .github; nếu chỉ kéo file đang nhìn thấy trên Windows, cần kiểm tra đã thêm thư mục này. Chưa có URL repository nên chưa có link job/commit GitHub đã chạy; kết quả Windows trong Actions phải chờ bạn push. Windows launcher thủ công chưa được kiểm tra trong môi trường này.

Chạy lại QA local khi môi trường đã có pytest:

```powershell
.\.venv\Scripts\python.exe scripts\run_qa.py
```

run_qa.py tạo manifest source, chạy toàn bộ pytest với database tạm, chạy demo_gd9_check.py riêng trong workspace tạm, rồi ghi GD9_QA_RESULTS.json, GD9_E2E_RESULTS.json, GD9_pytest.xml vào docs. Không huấn luyện vào runtime cá nhân. Đây là lệnh kiểm thử cho nhóm phát triển; cập nhật patch thông thường không cần chạy lại QA hoặc cài pytest.

## G07 — Release manifest

release_manifest.json chứa release_id từ hash các file code, tests, CI, model, data, reference, requirements và launcher; phiên bản frozen, hash policy selection, schema contract/version/hash. Không chứa runtime hay API key.

GO/NO-GO kiểm tra các file có trong manifest thực tế, không chỉ đọc một nhãn version. CMD được hash theo LF chuẩn hóa để bản đóng gói CRLF chạy trên Windows không bị báo lệch giả. Sau chỉnh code, checksum không còn khớp; chạy lại run_qa.py để tạo bằng chứng cho release mới, không chỉ sửa con số passed trong JSON.

Checksum không phải chữ ký số. Người có quyền sửa cả manifest và kết quả QA có thể làm giả bằng chứng; production cần kiểm soát repository, artifact signing và CI provenance riêng. Tài liệu/docs hướng dẫn không nằm trong source release_id, tránh vòng lặp khi QA tạo báo cáo; checksum cả gói nguồn có thêm trong GD9_FILE_MANIFEST.json.

## G08 — GO/NO-GO

Mở trang riêng **GO / NO-GO**, nhấn Kiểm tra lại. Kết quả dành cho **LOCAL_PROTOTYPE_DEMO**, gắn ca đang chọn và thời điểm kiểm tra.

Điều kiện bắt buộc: database/schema, model active, model ghim của ca và hash ghim, dependencies, file release khớp, ca đã chốt và đối soát khớp, Manager đã ký đúng snapshot, không có incident mở ở ca/hệ thống, QA cùng release có pytest exit 0/không lỗi và E2E pass.

Một điều kiện FAIL → NO_GO, xem bằng chứng và xử lý đúng nguyên nhân. Ca mới chưa đóng sẽ NO_GO cho nghiệm thu cuối ca dù vẫn có thể vận hành bình thường. NO_GO không tự hủy ca, đổi giá, đổi model hoặc bật/tắt AI; hard gates của GD6 vẫn thực thi nghiệp vụ.

Sau khi đủ bằng chứng mới hiện GO local. Cột production luôn NOT_ASSESSED. GO local không xác nhận việc cài đặt trên máy bạn, job GitHub đã chạy, backup runtime cá nhân mới nhất, độ chính xác AEON hay phê duyệt triển khai thật. Đó là những nghiệm thu riêng phải làm trong môi trường đích.

## G09 — Kịch bản demo cuối 10 phút

1. Mở GO/NO-GO ở ca mới: thấy NO_GO và ca chưa đối soát/chưa ký.
2. Duyệt kế hoạch → xác nhận chuẩn bị → bán mô phỏng → năm mốc M1 → đến 22:00 → chốt.
3. Báo cáo: đối soát từng SKU/giao dịch, Manager ký đúng snapshot.
4. GO/NO-GO: Kiểm tra lại, đọc từng bằng chứng; nếu không có incident và release/QA đúng thì GO local.
5. Copy Request ID của một request giao dịch trong Monitoring hoặc response API, tra audit/ledger tại trang readiness.
6. Mở Model Registry: chứng minh version ghim, ứng viên demo không được promotion, rollback có kiểm tra như GD8.
7. An toàn & sự cố: diễn tập lỗi dữ liệu/model theo GD6 trên ca mô phỏng riêng; quan sát manual/fallback/cảnh báo. Không cố tình sửa artifact gốc khi đang demo.
8. Xem docs/GD9_E2E_RESULTS.json: ca xuyên suốt, stale revision, Viewer bị từ chối, trace, backup/restore và model fault health 503 đã được kiểm thử trong DB tạm.
9. Nếu cần, chạy backup/restore trên bản sao sau khi dừng server, đối chiếu ca/tài khoản/model; không ghi đè runtime gốc.

## Trạng thái kiểm chứng

Bằng chứng chính: GD9_QA_RESULTS.json và GD9_E2E_RESULTS.json. Kiểm tra tương tác DOM được ghi riêng nếu có. API/security tests không thay thế pentest; DOM không thay thế kiểm tra layout bằng browser đồ họa. Không tuyên bố Actions/Windows/AEON đã pass khi chưa chạy tại các môi trường đó.
