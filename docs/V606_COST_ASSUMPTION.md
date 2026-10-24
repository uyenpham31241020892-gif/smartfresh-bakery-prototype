# Giá vốn mô phỏng 45% theo lựa chọn của người dùng

Báo cáo áp dụng **giá vốn đơn vị giả định = 45% giá niêm yết**, làm tròn từng đơn vị tới VND (half-up). Tổng chi phí chuẩn bị bằng giá vốn đơn vị nhân **toàn bộ lượng đã xác nhận chuẩn bị**, gồm cả bánh chưa bán. Không dùng giá sau giảm để hạ giá vốn; không trừ giá vốn hàng dư lần hai.

**Chênh lệch sau giá vốn giả định = doanh thu ghi nhận − tổng chi phí chuẩn bị giả định.** Đây chưa phải lợi nhuận ròng: phí hủy, lương, điện, thuê mặt bằng và các chi phí khác vẫn chưa xác định. Trong ca, chi phí chuẩn bị đã ghi nhận nhưng doanh thu còn tăng dần theo giao dịch, nên chênh lệch này chỉ là số tạm tính.

Ví dụ: chuẩn bị 10 chiếc, giá niêm yết 25.000đ; bán 6 chiếc ở giá 20.000đ, còn 4 chiếc. Giá vốn giả định = 112.500đ, doanh thu = 120.000đ, chênh lệch = 7.500đ. Giá vốn 45.000đ của 4 chiếc còn lại đã nằm trong 112.500đ, không trừ thêm.

Đây là lớp tính báo cáo theo giả định được người dùng cho phép, không phải chi phí đã khảo sát trong V6.06. Không sửa dữ liệu giao dịch, không đổi model/feature hoặc train lại. Áp dụng được ngay cho ca hiện tại và lịch sử khi tải lại báo cáo. Dấu kiểm đối soát bao gồm phiên bản giả định chi phí; biên bản cũ được giữ nhưng không tự ký thay người quản lý cho cách tính mới.

Nguồn công thức dùng chung: `services/costs.py`. Copilot nhận `financial_estimate` có nhãn `ASSUMED_NOT_VERIFIED`; `net_profit`, phí hủy và chi phí vận hành vẫn để thiếu. Các kiểm tra bao gồm bán giảm giá, tồn chưa bán, chống trừ hai lần, làm tròn và hiển thị trên trình duyệt.
