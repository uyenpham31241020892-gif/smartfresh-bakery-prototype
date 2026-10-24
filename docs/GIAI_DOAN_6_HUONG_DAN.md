# SmartFresh GD6 — Safety, Incident & Fallback
Nhóm B05, B07–B08, C và E · 22/10/2026

## 1. Bản này gồm những gì?
Full source tích hợp GD5 + bản sửa launcher Start-Gemini + GD6. Các model, SKU, dữ liệu demo và đầu ra đối chiếu V9 được giữ. GD6 thêm cơ chế backend và trang **An toàn & sự cố**, không nhồi các bảng quản trị vào Tổng quan.

Bản giao là source gọn: không kèm môi trường Python .venv, cache hoặc database phiên chạy của máy cũ. Model/dữ liệu có sẵn nên không phải upload để demo. Không tự kết nối POS, đổi giá ở AEON hoặc gửi thông báo ra ngoài.

## 2. Mở app lần đầu
1. Giải nén vào thư mục mới. Mở **Start-Gemini.cmd** nếu không muốn chạy Ollama; hoặc Start.cmd như trước. Lần đầu cần Python 3.12 và Internet để cài dependencies.
2. Khi terminal hiện địa chỉ, mở **http://127.0.0.1:8000**. Backend vẫn nghe loopback local.
3. GD6 lần đầu yêu cầu **Tạo tài khoản quản lý**. Tự chọn username 3–40 ký tự A–Z/0–9/._- và mật khẩu 8–128 ký tự. Không có tài khoản/mật khẩu mặc định.
4. Ghi nhớ thông tin này. Sau khi tạo, Manager đăng nhập và demo mở với 8 SKU như cũ. Không cần cấu hình Gemini để chạy M1/M2 hay tính năng an toàn.
5. Menu trái → **An toàn & sự cố** để xem các chức năng mới. Nhấn tên tài khoản ở cuối menu để đăng xuất.

Đây là tài khoản của workspace local, chưa phải tài khoản nhân viên AEON hoặc SSO của doanh nghiệp. Mật khẩu được băm bằng scrypt với salt riêng; cookie phiên HttpOnly, SameSite=Strict, hết hạn sau 8 giờ. Sai mật khẩu 5 lần thì khóa đăng nhập username đó trong 5 phút. Không lưu mật khẩu thô vào audit. Người có quyền sửa trực tiếp máy/database vẫn có đặc quyền hệ điều hành; prototype không chống lại chủ máy có quyền đó.

## 3. Phân quyền thực chất — Nhóm C
| Vai trò | Được làm | Bị chặn |
|---|---|---|
| Manager | Duyệt/từ chối sản lượng và giá; override trong hard rules; xác nhận áp dụng; đổi chế độ; xử lý sự cố; tạo tài khoản; quản lý AI/model | Không được vượt hard rules, dùng revision cũ, bỏ qua kiểm tra phục hồi |
| Staff | Xem, tạo ca thường, nhập dữ liệu/giao dịch, xác nhận đã chuẩn bị sau khi được duyệt, vận hành/chốt ca | Không duyệt/từ chối sản lượng hoặc giá, áp giá, tạo tài khoản, đổi chế độ, xử lý sự cố, thay model/AI settings |
| Viewer | Xem các ca/báo cáo/dữ liệu được chia sẻ trong workspace local | Không thay đổi dữ liệu hay thao tác vận hành |

Manager tạo Staff/Viewer trong khung **Tài khoản local** ở trang An toàn. Đăng xuất rồi đăng nhập từng tài khoản để trình diễn.

Các nút không đúng quyền được khóa ở UI. Quan trọng hơn, **gọi trực tiếp API cũng bị trả 403**. Gửi tên “Manager” hay header X-Role không cấp thêm quyền. Nếu chưa đăng nhập, API workspace trả 401. Các request ghi dữ liệu từ origin khác, kể cả khác port, bị chặn. Trang cũng không phục vụ hostname ngoài localhost/127.0.0.1 (testserver chỉ cho kiểm thử).

Đây chưa phải hệ thống phân quyền theo nhiều chi nhánh: tài khoản đã đăng nhập chia sẻ workspace trên máy này. Quản lý vòng đời nhân sự, đổi/quên mật khẩu, SSO và HTTPS production chưa thuộc GD6.

## 4. Ba chế độ vận hành
| Chế độ | Sản lượng M2 | Giá M1 | Ý nghĩa hành động |
|---|---|---|---|
| Assisted | Model hợp lệ đưa đề xuất; nếu lỗi thì rule fallback | AI đề xuất, Manager duyệt rồi mới xác nhận | Thay đổi trạng thái/giá trong ca local, không gửi POS |
| Manual | Rolling-7 + quy tắc baseline, mẻ 4 và sàn | Giữ mức đang hiệu lực hoặc đề xuất sàn bắt buộc; Manager có thể chỉnh trong giới hạn | Có thể vận hành bằng quy tắc; không giả vờ đây là AI |
| Shadow | Có thể tạo đề xuất để theo dõi | Có thể duyệt để diễn tập | Bước xác nhận giá ghi `shadow_only`, không đổi giá dùng cho giao dịch |

Manager đổi chế độ tại **Chế độ vận hành**, bắt buộc nhập lý do. Đề xuất giá đang chờ/đã duyệt sẽ bị đánh dấu hết hiệu lực khi đổi chế độ. Không thể lấy đề xuất cũ đó để áp dụng sau.

Nếu đổi chế độ khi kế hoạch sản lượng còn chưa duyệt, backend tính lại kế hoạch theo chế độ mới. Kế hoạch đã duyệt không bị âm thầm thay đổi. Khi chuyển Manual ở giữa ngày, tồn kho, doanh thu và giá đã áp dụng không bị reset. Ở mốc giá, hệ thống mới tạo đề xuất thủ công từ trạng thái hiện tại.

Tổng quan chỉ thêm thông báo ngắn khi Manual/Shadow/có sự cố, kèm nút mở trang chuyên sâu. Phần M2 fallback có nhãn Rolling-7 và không dùng TreeSHAP để giải thích quy tắc.

## 5. Model hash và fallback M2 — B05/B07
Khi khởi động, engine đối chiếu SHA-256 của m1.txt/m2.txt với manifest. Các lần inference và phục hồi cũng kiểm lại, nên thay model trên đĩa khi app đang mở không vượt qua được chỉ nhờ model đã cache.

Nếu file model sai hash hoặc model dự báo lỗi:
1. Không dùng file lỗi cho inference.
2. Ghi incident P1; chuyển ca đó sang Manual.
3. Với M2, nếu lịch sử vẫn vượt GD5, tính **trung bình bán trong 7 ngày trước** cho mỗi SKU.
4. Áp dụng quy tắc baseline sẵn có, sàn sản lượng và mẻ 4. Kế hoạch vẫn ở trạng thái chờ Manager duyệt.
5. Hiển thị `RULE_ROLLING7` và không tạo SHAP giả.

Fallback không có quyền bỏ qua GD5: lịch sử tương lai/quá cũ, forecast phát hành muộn hoặc đầu vào thiếu không đủ an toàn vẫn bị chặn. Rolling-7 là chính sách dự phòng PoC, không phải chứng cứ tối ưu trong vận hành AEON.

Trường hợp m1.txt/m2.txt sai checksum nhưng manifest/master còn đọc được, app vẫn có thể mở để xem incident và dùng rule fallback. Nếu manifest JSON hoặc cấu hình lõi bị mất/hỏng tới mức không thể xác định schema/chính sách, app dừng với lỗi ở console; cần phục hồi bundle nguồn tin cậy, không tự đoán cấu hình để tiếp tục.

SHA-256 giúp phát hiện sai khác so với manifest đang nạp; đây chưa phải chữ ký số hay hệ thống attestation của nhà cung cấp.

## 6. Fallback M1 và tồn kho — B08/E03/E04
Giá đang hiệu lực được giữ khi M1 lỗi; app không tự áp giá mới để che lỗi. Backend chuyển sang đề xuất thủ công với nguồn `MANUAL_RULE`.

Ví dụ:
- 19:30, mức đang chạy 0%: đề xuất thủ công có thể giữ 0%, hoặc Manager tăng trong trần 20%.
- Từ 21:00, mức đang chạy dưới 30%: không được gọi “giữ giá” để bỏ qua sàn. Hệ thống đưa mức tối thiểu hợp lệ lên danh sách chờ duyệt. Chỉ sau khi Manager duyệt và xác nhận thì giá local mới đổi.
- Manual vẫn giữ ladder 0/20/25/30/35/40/45/50%, cap theo slot, sàn từ 21:00 và không giảm ngược.

Nếu bán/tồn đã quá 30 phút trong ca live, chưa có nguồn bán hoặc drill đang đánh dấu tồn không đáng tin, **không đưa ra dòng gợi ý M1 nào**, kể cả Manual. Người quản lý không thể dùng Manual để vượt qua yêu cầu tin cậy tồn kho. Cần cập nhật giao dịch hoặc kiểm tra không có bán mới theo GD5. Dữ liệu tồn thực sự lệch kế toán cần đối soát/khôi phục nguồn đúng; GD6 không tự sửa tồn để cân bằng sổ.

## 7. Trung tâm sự cố — E01/E02/E05/E08
Một incident có ID, ca liên quan, loại, mức P1/P2, trạng thái, nội dung, người phụ trách, thời điểm và bằng chứng kiểm tra. Có thể có incident hệ thống khi model lỗi ngay lúc khởi động.

Các loại hiện có gồm M2_UNAVAILABLE, M1_UNAVAILABLE, STOCK_UNTRUSTED, ARTIFACT_MISMATCH/STARTUP_ARTIFACT và HARD_RULE_BLOCK.
- P1: lỗi model/checksum hoặc vi phạm hard rules có thể ảnh hưởng quyết định.
- P2: nguồn bán/tồn thiếu/quá hạn. Đây là phân loại demo local, chưa phải SLA doanh nghiệp đã được nghiệm thu.

Khi một vi phạm hard rule làm thao tác thất bại, thay đổi nghiệp vụ bị rollback; incident vẫn được lưu sau rollback. Lặp cùng loại sự cố chưa đóng trong cùng ca không tạo hàng loạt incident trùng. Request thất bại vẫn có audit API. Không phải mọi lỗi đánh máy hay revision cũ đều trở thành incident P1.

Các bước UI:
1. **Tiếp nhận**: Manager nhận trách nhiệm, ghi lý do. Open → Acknowledged.
2. **Khắc phục**: ví dụ nhập nguồn mới, phục hồi file model đúng hash hoặc gỡ cờ lỗi giả lập. Không chỉ viết “đã sửa” rồi đóng.
3. **Kiểm tra phục hồi**: chạy kiểm tra thực tế và lưu receipt. Trạng thái vẫn Acknowledged, chưa tự bật AI.
4. **Đóng sự cố**: chỉ được khi receipt còn hợp lệ. Acknowledged → Resolved.
5. **Assisted/Shadow**: Manager chủ động bật lại, có lý do. Chưa đóng hết sự cố liên quan thì bị chặn.

## 8. Kiểm tra phục hồi — E06
Backend kiểm:
- Hash model đúng và model có thể nạp.
- Không còn cờ lỗi diễn tập.
- Đối soát Prepared = Sold + Stock, số bán và doanh thu khớp ledger.
- Bán/tồn còn mới nếu đang ở giai đoạn M1 của ca live.
- Đầu vào snapshot không vi phạm thời gian/freshness của GD5.
- M2 thực sự chạy được và output đáp ứng mẻ/sàn.
- M1 thực sự chạy được trên trạng thái ca và đáp ứng ladder/cap/floor.

Receipt gắn revision, phiên bản điều khiển và hash model. Nếu bạn thay đổi dữ liệu/ca sau Verify, receipt cũ không được dùng để đóng incident; cần Verify lại. Khi đóng xong, mode vẫn Manual cho đến khi Manager chọn Assisted. Đây là lý do nút “Gỡ cờ lỗi” không phải nút “Bật lại AI”.

Ca legacy trước GD5 có thể thiếu provenance cần cho recovery; khi không kiểm được đầu vào, hãy tạo ca mới với dữ liệu hợp lệ thay vì coi receipt cũ là hợp lệ.

## 9. Diễn tập rollback — E07
Nút **Diễn tập rollback cô lập** chỉ dành cho ca mô phỏng. Nó không đổi model đang dùng:
1. Ghim ca và phiên bản hiện tại.
2. Chọn bundle V9 gốc làm ứng viên phục hồi.
3. Kiểm checksum.
4. Chạy smoke M2 (mẻ/sàn) và M1 (ladder/cap/floor).
5. Lưu bằng chứng drill vào audit.
6. Giữ nguyên active model; phục hồi thật vẫn cần Manager xác nhận qua luồng model sẵn có.

Receipt ghi rõ `changed_active_model: false`. Đây là diễn tập khả năng phục hồi, không được báo cáo là đã rollback production. Luồng promote/rollback model cũ vẫn có, nay chỉ Manager gọi được và vẫn kiểm checksum; vòng đời model đầy đủ thuộc giai đoạn sau.

## 10. Kịch bản demo cho nhóm
### A. Lỗi M2, fallback và phục hồi (dễ thử nhất)
1. Đăng nhập Manager, tạo ca mô phỏng mới; chưa duyệt sản lượng.
2. Vào An toàn & sự cố → **M2 lỗi → Rolling-7** → nhập lý do.
3. Xem incident P1, chế độ Manual, rồi qua Kế hoạch sản lượng thấy Rolling-7. Chưa có bánh nào tự được chuẩn bị.
4. Quay lại An toàn → **Tiếp nhận**.
5. **Gỡ cờ lỗi diễn tập** → nhập lý do.
6. **Kiểm tra phục hồi** → mở Bằng chứng kiểm tra.
7. **Đóng sự cố** → chọn **Assisted**, nhập lý do.
8. Kế hoạch còn chưa duyệt sẽ được tính lại bằng M2 AI. Incident cũ vẫn còn trạng thái Resolved trong lịch sử.

### B. Lỗi M1, giữ giá và manual override
1. Tạo ca mô phỏng, duyệt sản lượng, xác nhận đã chuẩn bị.
2. Chuyển đồng hồ tới 19:30; nếu đồng hồ tự chạy, dừng nó trước khi diễn tập.
3. An toàn → **M1 lỗi → Manual**. Xem incident và mức giá sản phẩm vẫn không đổi.
4. Màn Giảm giá: có đề xuất thủ công. Manager có thể chỉnh trong hard rules, nhập lý do, duyệt rồi xác nhận hành động.
5. Tiếp nhận → gỡ cờ → Verify → đóng → Assisted. Nếu còn đề xuất giá cũ, đổi mode sẽ làm nó hết hiệu lực; cần gợi ý mới ở bước vận hành tiếp theo.

### C. Tồn không đáng tin phải chặn cả manual
1. Dùng ca mô phỏng đã chuẩn bị và tới 19:30.
2. Chọn **Tồn kho không đáng tin**.
3. M1 không có dòng đề xuất để duyệt. Không tự sửa tồn hay áp giảm giá.
4. Tiếp nhận → gỡ cờ → Verify → đóng → Assisted. Đây là drill nên gỡ cờ biểu thị đã sửa nguồn giả lập; với dữ liệu thật phải cập nhật nguồn đúng.

### D. Quyền duyệt thực sự
1. Manager tạo tài khoản Staff ở trang An toàn.
2. Nhấn tên tài khoản ở menu để đăng xuất; đăng nhập Staff.
3. Mở ca mới/chưa duyệt: Staff xem được nhưng nút duyệt bị khóa.
4. Nếu gửi POST trực tiếp vào API plan_approve/price_approve/price_apply, backend vẫn trả 403. Đổi chữ “Manager” trên giao diện không cấp quyền.
5. Tạo thêm Viewer để kiểm tra quyền chỉ xem.

### E. Shadow
Tạo ca mô phỏng, chọn Shadow trước khi vận hành, duyệt và xác nhận chuẩn bị. Ở mốc giá, duyệt một mức khác giá hiện tại và xác nhận. Nhật ký quyết định ghi shadow_only; giá dùng tính tiền không đổi. Shadow không phải Assisted đã publish.

## 11. Audit: ai đã làm gì?
Nhật ký ca ghi identity từ phiên đăng nhập, thời điểm, revision, model/version/hash, feature snapshot, giá và đề xuất trước/sau, lượng chuẩn bị/duyệt và lý do. Audit hệ thống có đăng nhập, tạo tài khoản, API từ chối quyền, incident, kiểm tra phục hồi và rollback drill. Backend realtime dùng actor system, không giả danh người quản lý.

Audit cũ trước GD6 không được tự gán người duyệt hồi tố. SQLite local không phải kho audit chống sửa bởi chủ máy; logging tập trung bất biến và phân quyền vận hành production còn ở giai đoạn triển khai.

## 12. Giữ dữ liệu phiên cũ nếu cần
Bản ZIP không chứa database cũ. Nếu chuyển từ GD5 trên máy bạn:
1. Dừng toàn bộ cửa sổ server cũ trước.
2. Sao lưu nguyên thư mục dự án cũ.
3. Copy thư mục runtime của bản GD5 vào thư mục source GD6 mới trước khi chạy. Không thay bằng runtime từ máy khác và không copy .venv cũ.
4. GD6 thêm bảng auth/safety khi mở; dữ liệu sessions cũ không bị xóa. Bạn vẫn tạo Manager local nếu database đó chưa có users.
5. Tạo một ca mô phỏng mới để diễn tập GD6. Ca đã chốt/legacy không được tự sửa lịch sử hoặc tạo receipt hồi tố.

Kiểm thử migration đã đối chiếu các JSON session trong database kèm bản prototype(4) trước/sau khởi tạo auth và chúng không đổi. Luôn giữ bản sao cũ của chính bạn trước khi chuyển.

## 13. Bằng chứng kiểm thử và cách chạy lại
- Bộ regression: **110 bài pass**, gồm kiểm thử cũ và GD6 (auth, role, checksum, fallback, stale stock, hard rules, shadow, incident lifecycle, receipt hết hiệu lực, rollback drill, bảo toàn database cũ).
- Kiểm thử DOM: thiết lập Manager, đăng nhập, diễn tập lỗi M2, đủ vòng khắc phục/phục hồi, tạo/đăng nhập Staff, nút duyệt bị khóa, đi qua 9 màn hình, không có lỗi JavaScript.
- Chạy `python scripts/demo_gd6_check.py` để diễn tập API end-to-end trên database tạm, không đổi ca đang dùng. Script dùng mật khẩu ngẫu nhiên chỉ trong test.
- Chạy `python -m pytest -q` sau khi cài requirements-dev.txt. Bài migration cần ZIP gốc ở vị trí workspace; khi không có ZIP đó, bài này skip và các bài còn lại vẫn chạy.
- Không xác nhận visual QA bằng trình duyệt đồ họa/Windows CMD trong môi trường này: bộ cài Chromium tải lỗi, nên DOM không thay thế kiểm tra bố cục thực tế. Launcher giữ bản sửa tự cài dependencies đã bàn giao.

GD6 không bao gồm dashboard drift (GD7), kiểm định holdout mới/chu kỳ model đầy đủ (GD8), hoặc chứng nhận go-live/security production (GD9). Không có kết nối SSO/POS/AEON thật. Các cảnh báo và hành động hiện nằm trong workspace local, không gửi thông báo ra ngoài.
