# Kiểm tra JOINT và POS mô phỏng liên tục trong 30 ngày

Chạy `py -X utf8 scripts/audit_joint_month.py` với seed 42 trong database tạm. Mỗi ca được chốt trước khi nối sang ngày tiếp theo, từ **01/05 đến 30/05/2022**, gồm cả **04/05**. [Dữ liệu từng ngày và SKU](JOINT_MONTH_AUDIT.json) lưu nhu cầu nền của POS riêng cho bước đánh giá sau ca; JOINT không nhận được con số đó khi lập kế hoạch. [Lượt chạy trước khi thêm bộ chặn sai lệch](JOINT_MONTH_GENERATED_BEFORE_GUARD.json) dùng cùng seed và cùng nhu cầu nền để so sánh.

| Chính sách | Chuẩn bị | Bán | Tồn cuối ngày | Bán / chuẩn bị | SKU-ngày hết hàng | Sai lệch tuyệt đối chuẩn bị − nhu cầu nền, bình quân/ngày |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trước hiệu chỉnh | 30.968 | 26.617 | 4.351 | 86,0% | 107 | 370,9 bánh |
| Có chặn theo baseline | 39.896 | 34.541 | 5.355 | 86,6% | 36 | 212,3 bánh |

Trong lượt có hiệu chỉnh, 15 ngày đầu và 15 ngày cuối lần lượt có **21 và 15 SKU-ngày hết hàng**; sai lệch tuyệt đối trung bình lần lượt **233,0 và 191,6 bánh/ngày**. Tồn tăng thêm 1.004 bánh trong 30 ngày so với lượt trước, nên đây là đánh đổi giữa thiếu hàng và hủy bánh, không phải cải thiện mọi chỉ số. Hai lượt đều dùng cùng thị trường POS tổng hợp; kết quả chỉ chứng minh tính ổn định nội bộ của kịch bản, **không phải hiệu quả đã kiểm định tại AEON**.

## Nguyên nhân và sửa đổi

Trước đây POS lấy sự kiện trong file V4 cố định. File không có 04/05, nên ứng dụng bỏ qua ngày dù POS được kỳ vọng hoạt động liên tục. Giờ worker POS V2 sinh cơ hội mua theo từng SKU và từng khoảng thời gian từ baseline đến 30/04, thứ trong tuần, ngày nghỉ, seed và mức giá đã áp dụng. Nhu cầu nền được cố định tại đầu ngày và không phụ thuộc lượng JOINT chuẩn bị hay hàng còn lại. Worker chỉ trả sự kiện trong khoảng thời gian đã trôi qua. Bản mô phỏng cũ vẫn giữ để đọc ca cũ; khi nối từ ca 03/05 cũ, ứng dụng tạo ca **04/05** bằng POS V2 và ghi dấu đổi nguồn trong provenance.

Vòng lặp trước đây đưa doanh số ca đã hết hàng vào feature như nhu cầu thật; đồng thời nhánh JOINT không nhận đủ lịch sử để đối chiếu baseline. Doanh số bị chặn thấp dần có thể kéo kế hoạch cuối tuần xuống rất mạnh. Chính sách mới truyền lịch sử đã chốt cho JOINT, giữ doanh số ngày hết hàng là **cận dưới**, bỏ ngày đó khỏi ước lượng tỷ lệ cập nhật từ các ngày bán đủ, và chặn dự báo quanh mức lịch sử baseline cùng loại ngày. Chính sách phân biệt thứ Sáu với thứ Bảy/Chủ nhật khi tính neo baseline. Model JOINT vẫn dùng trọng số cố định; đây là **hiệu chỉnh đầu ra có kiểm soát**, không phải tái huấn luyện hàng ngày.

Ngày **02–03/05/2022** được giả định là ngày nghỉ bù khi sinh POS mới. Nhu cầu nền mô phỏng lần lượt **1.826 và 1.766** bánh, còn 04/05 là **744** bánh. Chênh lệch phản ánh nhóm ngày nghỉ so với thứ Tư trong baseline dùng để sinh khách; dữ liệu hiện có không đủ chứng minh đó là nhịp mua thực tại AEON. Các ca cũ của người dùng và số bán đã chốt được giữ nguyên. Thời tiết của ngày thiếu trong bộ V4 dùng proxy từ dữ liệu quá khứ, có nhãn **chỉ dành cho mô phỏng**; đó không phải dự báo lịch sử có thời điểm phát hành được xác minh.

Để kiểm định độ chính xác thực tế hoặc học trọng số an toàn, cần POS AEON có dấu thời gian, giá, chuẩn bị, tồn/hết hàng và ít nhất vài chu kỳ cùng thứ. Khi hết hàng, số bán không cho biết chính xác bao nhiêu khách đã bỏ đi; không dùng trực tiếp số bán đó làm nhãn nhu cầu đầy đủ.
