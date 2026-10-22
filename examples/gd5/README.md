# Bộ thử Giai đoạn 5
Tất cả là dữ liệu synthetic phục vụ kiểm tra, timestamp khai báo để test, không phải bằng chứng POS/JMA.
Chọn ngày mục tiêu **16/08/2022**, vào Dữ liệu đầu vào và tải một tệp.
- 01_valid_synthetic.xlsx: preview hợp lệ → xác nhận → tạo ca live mới; PASS kiểm tra khai báo theo thời gian, không xác thực nguồn thật.
- 02/03/04: chặn forecast phát hành muộn, forecast quá 48h, dữ liệu sẵn có sau cutoff.
- 05: cách ly cột hidden_demand; không cho model nhìn đáp án.
- 06: chặn lịch sử ngày hiện tại.
- 07: preview cảnh báo từng SKU, xác nhận bị BLOCKED vì lịch sử quá cũ; không tạo ca mới.
Ca demo mặc định không yêu cầu bất kỳ tệp nào trong thư mục này.
