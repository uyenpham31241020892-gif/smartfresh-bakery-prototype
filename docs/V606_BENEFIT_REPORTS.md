# Báo cáo phân tích và kiểm tra lợi ích giảm giá — v6

## Quyết định giá

19:30 chỉ là mốc đánh giá. V6.06 chưa có bằng chứng phản ứng giá nhân quả, và simulator busy4 hiện không tạo thêm lượt mua khi giảm giá. Vì vậy, giảm từng nấc nhỏ có thể chỉ làm tiền thu giảm trong khi số bán/tồn không đổi. Bản v6 giữ giá nếu chưa có lợi ích tăng thêm được xác minh, thay vì tự giảm vì đến giờ hoặc vì tồn dư.

M1 vẫn đọc số bán và dự báo dưới hành động đã ghi nhận; các phương án giá chỉ là tham khảo cho kiểm tra hòa vốn. Gate ghi giá hiện tại, giá thử, phần nhượng giá trên cùng số bán kỳ vọng và số bánh cần bán thêm để hòa vốn doanh thu. Đây **không** phải số bán thêm đã chứng minh.

Ví dụ kỳ vọng bán tiếp 50 bánh, giá 100 giảm còn 80: nhượng 1.000 trên cùng lượng bán, cần bán thêm ít nhất 13 bánh để bù. Giá vốn toàn bộ hàng chuẩn bị đã phát sinh theo giả định 45%, không trừ lần nữa như chi phí sản xuất mới cho hàng có sẵn. Phí hủy và vận hành chưa biết, không tự thêm vào lợi ích.

Guard áp dụng cả cho đề xuất tương lai của engine cũ đang ghim. Đề xuất AI cũ chưa áp dụng mà thiếu bằng chứng bị chặn ở bước duyệt/áp dụng và được đánh giá lại có audit; không sửa hóa đơn, tồn hoặc giá đã có hiệu lực. Quyết định thủ công có chủ đích không bị giả làm đề xuất AI đã chứng minh lợi ích.

## Ba tab báo cáo

- **Tổng quan**: doanh thu/lượng bán, chuẩn bị/tồn theo ngày và giờ; so ngày trước, cùng thứ tuần trước và cùng ngày tháng trước; khoảng 7/30/90 ngày.
- **Giá & chiết khấu**: giá thực thu bình quân gia quyền, giá trị giảm so niêm yết, lượng bán ở giá giảm/nguyên giá, diễn biến giá bình quân qua ngày/giờ; phân rã chênh doanh thu thành lượng bán và giá bình quân/cơ cấu món. Các thành phần làm tròn VND vẫn cộng đúng tổng chênh lệch.
- **Từng loại bánh**: lọc SKU, biểu đồ đóng góp doanh thu, bán/tồn trên lượng chuẩn bị, lịch sử riêng, doanh thu cộng dồn ngày đã chốt; bảng doanh thu, giá bình quân, chiết khấu và chênh sau giá vốn giả định.

Không coi ASP giảm là toàn bộ tác động giá: thay đổi cơ cấu món cũng làm ASP đổi. Giá trị giảm so niêm yết tính trên đúng lượng đã bán không tự chứng minh doanh thu sẽ thu thêm nếu giữ giá ở thị trường thật. Tồn cuối ngày chưa phải số hàng đã hủy vật lý. Tổng hợp nhiều ngày chỉ gồm ca đã chốt, ca đang bán ghi tạm tính.

## AI cạnh biểu đồ

Copilot tự đọc đúng tab, khoảng xem và SKU qua công cụ `get_business_report`, có ảnh chụp ngày/giờ rõ ràng. Nút **Phân tích lại số mới** lấy snapshot mới; **Hỏi sâu hơn** mang cùng phạm vi vào chat. Phân tích được cache theo phạm vi, không gọi lại mỗi giây khi đồng hồ mô phỏng chạy.

Đã phát hiện trong thử nghiệm rằng văn bản LLM tự do có thể nhầm phút 1320 thành giờ 13:20, hoặc tự quy ASP giảm thành tác động giá. Vì vậy dùng đầu ra có schema: **AI chọn các trọng tâm và hành động ưu tiên dựa trên dữ liệu; máy chủ ghép số liệu, thời điểm và diễn giải được kiểm tra theo snapshot**. Không công bố nhận xét tự bịa con số, ngày giờ hoặc quan hệ nhân quả. Model phải gọi công cụ báo cáo; đáp án không hợp lệ bị từ chối, không dùng mẫu số liệu giả thay cho AI.

Đã gọi Ollama `qwen3.5:4b` thật và xác nhận công cụ báo cáo được đọc, thời điểm 22:00 hiển thị đúng. Lỗi kết nối/không đạt schema hiển thị rõ. Đây là phân tích hỗ trợ đọc báo cáo, không tự duyệt giá hay thay đổi sản lượng.

Các dữ kiện chỉ đến từ sổ quan sát và aggregate đúng nhánh/thời điểm. Không đọc private, nhãn tương lai, nhu cầu ẩn hoặc lost-sales để đưa cho model/LLM. Chi tiết ngày trong context AI giới hạn 30 ngày gần nhất; tổng hợp kỳ vẫn gồm toàn bộ ngày đã chốt trong khoảng chọn.

Mở lại tại http://127.0.0.1:8000 bằng Ctrl+F5 rồi chọn **Báo cáo hiệu quả**. Không cần tạo lại ca để xem báo cáo mới.
