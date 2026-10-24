# Báo cáo hiệu quả theo thời gian

Mở **Báo cáo hiệu quả** trong prototype. Khoảng xem 7, 30 hoặc 90 ngày; chọn biểu đồ doanh thu hoặc chuẩn bị/bán/tồn. Biểu đồ thứ hai trình bày bán lũy kế và tồn theo giờ của ca đang chọn. Di chuột vào điểm để xem số liệu, hoặc mở bảng từng ngày.

Bốn chỉ số doanh thu, lượng bán, chuẩn bị và tồn có thay đổi tuyệt đối và phần trăm so với ngày trước, cùng thứ tuần trước hoặc cùng ngày tháng trước. Đây là so sánh **từng ngày**, không phải tổng tuần/tháng. Nếu tháng trước không có ngày tương ứng, dùng ngày cuối tháng. Phần trăm = (hiện tại − mốc trước) / |mốc trước| × 100. Mốc trước bằng 0 không tính phần trăm.

Chỉ so sánh ca đã chốt và đối soát khớp. Ca chưa chốt vẫn xuất hiện với điểm rỗng, số tạm tính và biểu đồ trong ngày; chưa công bố phần trăm so với cả ngày đã kết thúc. Ngày thiếu là khoảng trống, không phải doanh số 0. Tồn cuối ngày chưa đồng nghĩa hàng đã hủy.

Nguồn là sổ ca SQLite đã lưu. Không tạo giao dịch hoặc lịch sử giả, không ghép lịch sử train vào hiệu quả vận hành. Chỉ lấy cùng chế độ và checksum trọng số model; mô phỏng còn khớp seed, phiên bản và hash thị trường. Policy cung ứng có thể thay đổi: bảng ngày ghi phiên bản, và thay đổi kinh doanh không được gọi là tác động nhân quả. Ca cũ thiếu checksum dùng cùng phiên bản làm phạm vi dự phòng. Mỗi ngày lấy ca đã chốt tạo gần nhất, riêng ngày đang xem lấy chính ca được chọn. Không cộng nhiều lần chạy lại của một ngày. Ca lệch sổ bị loại.

Endpoint đọc: `GET /api/business-report/{sid}?days=30`, yêu cầu đăng nhập như dashboard. Không ghi sổ, không đổi model, feature hoặc dữ liệu train. Lịch sử tải lại khi ca thay đổi và mỗi 15 giây khi đang mở báo cáo.
