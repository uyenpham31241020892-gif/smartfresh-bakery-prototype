# GD9.2 — Sàn sản lượng khuyến nghị và quyền Manager

## Đổi gì

Sàn90%baseline vẫn được tính/hiển thị để giữ bằng chứng khuyến nghị. Đề xuất tự động M2/Rolling7 giữ công thức cũ; Manager được duyệt lượng thấp hơn sàn khi có lý do. Không tự giảm tất cả SKU hay sửa model/dữ liệu.

Bắt buộc: số nguyên dương, mẻ4, tối thiểu4. Giới hạn100.000 là bảo vệ nhập liệu kỹ thuật hiện có, không được gọi là công suất sản xuất thật. Chưa có giới hạn sản xuất doanh nghiệp đã xác minh nên không đặt thêm sàn/trần nghiệp vụ giả định.

Chỉ Manager được duyệt, backend chặn cả khi gọi API trực tiếp. Dưới khuyến nghị là quyết định hợp lệ có cảnh báo, không tạo incident chỉ vì thấp hơn khuyến nghị. Các hard rules M1 về giá vẫn bắt buộc như trước.

## Dùng thế nào

1. Đăng nhập Manager; mở ca mới hoặc ca còn Chờ duyệt sản lượng.
2. Vào Kế hoạch sản lượng: cột đổi thành Sàn khuyến nghị. Ví dụ BK-001 còn hiển thị60, đề xuất gốc60.
3. Sửa Số duyệt thành48 hoặc52. Cảnh báo Dưới khuyến nghị60 xuất hiện; số50 vẫn không hợp lệ vì không chia hết4.
4. Nhấn Duyệt kế hoạch. Hộp xác nhận liệt kê SKU, đề xuất, sàn khuyến nghị và lượng duyệt mới; lưu ý nguy cơ hết hàng.
5. Nhập lý do như “Ca trước tồn nhiều; Manager chọn48 để theo dõi”. Không có lý do thì không duyệt được.
6. Xác nhận duyệt. Chưa ghi sản xuất; còn bước Xác nhận đã chuẩn bị.
7. Xác nhận đã chuẩn bị: tồn/chuẩn bị của BK-001 là48, không bị đưa trở lại60. Nếu các SKU khác giữ nguyên, tổng284 thay vì296.
8. Vận hành M1, bán, chốt và đối soát như cũ. Giá vốn giả định, tồn và waste lấy lượng chuẩn bị thực sự đã duyệt.

Có thể duyệt trên/sát/dưới khuyến nghị theo từng SKU, giữ nguyên sản phẩm khác. Áp dụng cả Assisted và Manual; không cần đổi Manual chỉ để giảm lượng. Model không bị huấn luyện lại vì Manager điều chỉnh. Snapshot/dự báo/khuyến nghị gốc không bị viết đè thành con số Manager chọn.

## Bằng chứng

State lưu production_approval: phiên bản quy tắc mới, người duyệt, thời điểm, lý do, từng SKU với lượng khuyến nghị, sàn khuyến nghị, lượng duyệt, chênh lệch và cờ dưới sàn. Audit PLAN_APPROVE chứa cùng bằng chứng cùng before/after, revision, request ID, model và feature snapshot. Trang M2 hiển thị lại điều chỉnh đã duyệt. Quyết định giữ sau restart.

Quyết định hạ chuẩn bị có thể tăng stockout/lost sales; theo dõi đồng thời waste và guardrails sau ca, không coi ít hàng dư là tự động tối ưu. Chưa có bằng chứng cải thiện lợi nhuận AEON từ bản cập nhật này.

Ca đã duyệt/chuẩn bị/chốt không bị tự đổi khi cài patch. Tính năng áp dụng ở bước duyệt ban đầu; nếu cần thử lại, tạo ca mới. Không sửa hồi tố sản lượng đã sản xuất hoặc ledger cũ.

## Cập nhật

Patch tích lũy dùng trên GD9 hoặc GD9.1 đã gửi, gồm cả sửa dropdown/chế độ giá GD9.1. Dừng server, backup project, giải nén patch ra ngoài rồi chép toàn bộ nội dung vào thư mục có app.py, merge/replace. Giữ .venv/.tools/.env/runtime; không cần cài thư viện mới. Restart launcher cũ rồi Ctrl+F5. Nếu tự sửa code sau bản bàn giao, đối chiếu file trùng tên trước khi thay.

Full source giữ model/data và mọi phần trước, không chứa environment/database cá nhân. Patch bảo toàn runtime/tài khoản/lịch sử, không drop bảng. Manifest GD9/GD9.1 cũ là lịch sử; GD9_2_FILE_MANIFEST và release_manifest mới là bản hiện hành.

## Kiểm chứng

Bằng chứng mới: GD9_QA_RESULTS.json, SOFT_FLOOR_DOM.json. Kiểm tra gồm Manager48/52 dưới60, lý do bắt buộc, chặn Staff, bội4/dương/giới hạn nhập liệu, atomic rejection, audit, actual inventory, M1→đóng ca→đối soát→restart, và fallback Manual. DOM thử cả invalid50, cảnh báo và hộp xác nhận, lý do trống, duyệt48, actualprepared48/tổng284. Các kiểm tra dùng database tạm.

Chưa xác minh browser đồ họa/Windows trực tiếp. Các hướng dẫn cũ nói sàn90% bắt buộc được thay thế bởi quy tắc GD9.2 này; dữ liệu/model/policy pricing và F04 không đổi.
