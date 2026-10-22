# GD9.1 — Manager chọn giá tại M1

## Cập nhật

Dừng server Ctrl+C; sao lưu project. Chép toàn bộ nội dung PATCH vào thư mục GD9 chứa app.py, gộp thư mục và thay file trùng tên. Giữ .venv/.env/runtime. Chạy launcher cũ rồi Ctrl+F5. Không cần cài thư viện hay tạo environment. Full source gồm phần trước và bản sửa; không chứa runtime hoặc environment cá nhân.

## Đã sửa

- Chuyển ba nút Assisted / Manager tự quyết Manual / Shadow từ Safety sang trang Giảm giá cuối ngày, hiển thị cả khi chưa tới giờ/chưa có feed.
- Tránh dựng lại dropdown mỗi giây lúc đang mở/chọn; giữ bản nháp sau khi blur. Poll không đè một request vừa trả về vào thao tác chỉnh đang diễn ra. Lỗi revision từ phiên khác vẫn bị backend chặn và buộc xem lại.
- Đổi mode từ giao diện tạm dừng clock; pending cũ hết hiệu lực; tại 19:30–trước22:00 tạo ngay pending mới để chỉnh được.
- Nút “Tạo lại bảng chỉnh giá tại …” cho Manager mở lại bảng ở phút hiện tại sau khi đã duyệt/áp dụng. Không sửa ngược giao dịch hoặc ca đã chốt.
- Manual hiển thị bán 30/60 phút tính từ sổ, không hiện null/null; nhãn “Quy tắc giữ giá” thay AI đề xuất khi nguồn là MANUAL_RULE.
- Mỗi SKU được chọn riêng; không ép tất cả cùng mức. Các SKU không chỉnh theo mức mặc định còn hợp lệ. Lý do, người duyệt, model/proposal/revision vẫn ghi audit.
- Giữ nguyên model/dữ liệu, simulator, hàm mục tiêu, thang giá/sàn/trần. Bản sửa không tuyên bố tăng doanh thu hoặc xóa hàng tồn.

Mode vẫn ở cấp ca như trước; đổi trước duyệt M2 có thể tính lại kế hoạch theo fallback. Sản lượng đã chuẩn bị không bị viết lại khi đổi mode cuối ca. Safety vẫn giữ incidents, recovery, quyền, fault drills và liên kết sang M1.

## Cách dùng

1. Ca đang mở, từ 19:30 đến trước22:00, đăng nhập Manager.
2. Ngay trang M1 chọn Manager tự quyết · Manual, nhập lý do. Clock tạm dừng.
3. Chọn mức Giảm duyệt cho từng SKU cần xử lý. Có thể chỉnh ngay trong Assisted nếu không muốn đổi mode.
4. Duyệt đề xuất giá, nhập lý do điều chỉnh, xác nhận.
5. Áp dụng giá đã duyệt, xác nhận. Chỉ giao dịch mới dùng giá mới.
6. Nhấn Bán tự động để chạy lại nếu cần, hoặc chuyển mốc thủ công.
7. Muốn chỉnh thêm trong cùng mốc: Tạo lại bảng chỉnh giá, xem lại toàn bộ bảng và duyệt/áp dụng lại. Đề xuất cũ không dùng lại được.

19:30 trần20%;20:00 trần25%;20:30 trần35%;21:00 sàn30%/trần45%;21:30 sàn30%/trần50%. Giữ thang0/20/25/30/35/40/45/50 và không giảm ngược. Manual không phải bỏ qua hard rules. Nếu muốn thay chính sách để 50% từ21:00, đó là thay policy riêng cần thống nhất, không nằm trong bản sửa này.

Ảnh22:00 “Đã chốt ngày” chỉ đọc. Cập nhật phần mềm không làm ca cũ thay kết quả; hãy tạo ca thử mới hoặc mở ca chưa đóng. Không sửa giá hồi tố để làm báo cáo đẹp hơn.

## Vì sao AI ít/chưa chọn50%

Kiểm tra ca tổng hợp riêng ngày16/08/2022 seed42 với model frozen cho thấy50% có trong candidate lúc21:30 của cả8SKU nhưng30% được chọn. Ví dụ BK-001 tồn18: phương án30% dự kiến doanh thu phần còn lại khoảng5657đ, còn50% khoảng4745đ; lượng kỳ vọng bán chỉ tăng khoảng0,825→0,968 bánh. Đây là kỳ vọng nên có số lẻ, không phải sổ giao dịch thật. Xem PRICING_50_DIAGNOSTIC.json.

Phản ứng dự báo gần phẳng từ30% đến45%, tăng rất ít ở50%; số lượt mua mô phỏng cuối ngày ít. Tồn cao không tự làm optimizer chọn giảm sâu nếu mô hình không dự báo bán được nhiều hơn. Mục tiêu hiện ưu tiên doanh thu kỳ vọng, có phạt tồn cuối mức0,025×giá tham chiếu×lượng dư; không phải mục tiêu “xả hết hàng bằng mọi giá”. Không kết luận toàn bộ lỗi ở data từ một ảnh.

Ca tái lập còn cho thấy tổng M2 forecast≈200,97 nhưng tổng sàn=296 và prepared=296; cả8SKU đều bị sàn90%baseline làm tròn mẻ chi phối. Đây là bằng chứng cụ thể cần xem lại calibration của sàn sản lượng trước khi chỉ tăng giảm giá. Không suy ra database ca trong ảnh hoàn toàn giống đầu vào này.

Ca chẩn đoán tổng hợp riêng cho296chuẩn bị/195bán/101dư; không phải truy xuất database ca trong ảnh (194bán/102dư). Không trộn các kết quả này.

## Đọc ảnh báo cáo người dùng

296: số đã xác nhận chuẩn bị.194: số bánh đã bán ghi trong sổ.65,5%=194/296.102: hàng dư=296−194, tương đương34,46%.2.965.310đ: doanh thu giao dịch đã ghi, chưa trừ chi phí.194dòng: số dòng ledger, không suy ra194khách duy nhất.

2.100.960đ: giá vốn sản xuất GIẢ ĐỊNH,45%giá tham chiếu nhân toàn bộ lượng chuẩn bị theo SKU, gồm cả bánh không bán.864.350đ=2.965.310−2.100.960: contribution trước overhead, dương, khoảng29,15%doanh thu; không phải lợi nhuận ròng. Nếu chi phí vận hành thực vượt khoản này thì có thể lỗ; ảnh không cung cấp số đó. Không trừ giá vốn hàng dư lần hai vào contribution vì toàn bộ sản xuất đã được tính.

0lượt ở Chất lượng phục vụ: simulator không ghi nhận nhu cầu đủ điều kiện bị mất do hết hàng. Không có nghĩa0tồn,0waste hoặc mô hình tốt. Trong một ca chỉ có một seed, đủ phục vụ nhưng sản xuất dư có thể cùng xảy ra.

## Hướng cải thiện có căn cứ

Sửa quyền thao tác trước; sau đó tách: lượng M2, phản ứng giá M1, số/nhịp khách simulator, mục tiêu optimizer và policy caps. Đọc forecast/buffer/floor để biết thành phần nào đẩy chuẩn bị lên; kiểm tra holdout theo SKU và theo mốc giảm. Kiểm chứng độ co giãn và khách cuối ngày bằng dữ liệu thật/controlled trials trước khi chỉnh model hoặc simulator.

Nếu mục tiêu nhóm ưu tiên giảm waste, cần hiệu chỉnh đánh đổi doanh thu–waste–lost sales và kiểm tra ứng viên trên nhiều ngày/seed/holdout độc lập. Không tăng lượt mua giả hoặc ép50%để làm đẹp KPI. Chưa có bằng chứng bản sửa giao diện sẽ nâng lợi nhuận;50%không tự tạo khách.

F04 vẫn bỏ khỏi giao diện. Bộ kiểm thử/rà soát mới: GD9_QA_RESULTS.json; DOM: MANAGER_PRICING_DOM.json. Các bằng chứng GD9 cũ giữ làm lịch sử; QA hiện tại gắn release_id mới. Windows/browser đồ họa chưa được kiểm tra trực tiếp.
