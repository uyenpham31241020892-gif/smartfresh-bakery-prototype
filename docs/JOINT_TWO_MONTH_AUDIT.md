# Đối chiếu vận hành JOINT, 01/07–31/08/2022

Đã chạy và chốt liên tục 62 ca JOINT bằng POS mô phỏng V3. Cùng 62 ngày được chạy độc lập với **baseline cùng thứ ×10**, dùng cùng seed 42, cùng nhu cầu nền theo SKU, cùng thời tiết và cùng chính sách giá M1. Baseline chốt trước toàn bộ lượng mẻ và nhận lúc 14:00/17:00; JOINT chỉ đặt mẻ bổ sung 14:00/17:00 sau khi đọc POS đã phát sinh lúc 12:00/15:00. Ca 01/09/2022 ở trạng thái chờ duyệt. Lịch sử 62 ca đã được nhập vào database ứng dụng sau khi sao lưu bản V2 cũ.

| Giai đoạn | Chính sách | Chuẩn bị | Bán | Bánh hủy | Doanh thu | Lãi góp mô phỏng | SKU-ngày còn hàng lúc 21:30 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tháng 7 | JOINT | 29.916 | 28.174 | 1.742 | 723.845.045 ₫ | 360.778.041 ₫ | 196/217 (90,32%) |
| Tháng 7 | Baseline ×10 | 30.020 | 27.981 | 2.039 | 716.345.685 ₫ | 352.210.119 ₫ | 178/217 (82,03%) |
| Tháng 8 | JOINT | 28.392 | 26.687 | 1.705 | 686.642.060 ₫ | 342.385.726 ₫ | 188/217 (86,64%) |
| Tháng 8 | Baseline ×10 | 29.220 | 26.802 | 2.418 | 685.209.725 ₫ | 330.588.869 ₫ | 183/217 (84,33%) |
| **62 ngày** | **JOINT** | **58.308** | **54.861** | **3.447** | **1.410.487.105 ₫** | **703.163.767 ₫** | **384/434 (88,48%)** |
| **62 ngày** | **Baseline ×10** | **59.240** | **54.783** | **4.457** | **1.401.555.410 ₫** | **682.798.988 ₫** | **361/434 (83,18%)** |

JOINT giảm **297 bánh hủy** trong tháng 7 và **713 bánh** trong tháng 8, tổng cộng **1.010 bánh (22,66%)**. Doanh thu hơn baseline **7.499.360 ₫** trong tháng 7, **1.432.335 ₫** trong tháng 8; lãi góp hơn tương ứng **8.567.922 ₫** và **11.796.857 ₫**. Cả hai tháng đều qua cổng kiểm tra bắt buộc: bánh hủy thấp hơn, doanh thu và lãi góp không thấp hơn baseline, và ít nhất 80% SKU-ngày còn hàng lúc 21:30.

Mức giảm hủy không xảy ra từng ngày: JOINT hủy ít hơn ở **42/62 ngày**, nhiều hơn ở **19/62 ngày**, bằng nhau 1 ngày. Số SKU-ngày từng hết hàng là **128** so với baseline **125**, tăng 3; mẻ bổ sung có điều kiện có thể để hụt tạm thời trước khi nhận. Vì vậy kết quả này chưa chứng minh mọi ngày đều phục vụ tốt hơn. Tỷ lệ có hàng lúc 21:30 là số SKU-ngày thực tế trong mô phỏng, khác với xác suất 80% M1 ước tính khi quyết định giá.

## Vì sao biểu đồ cũ bị đỉnh lặp

POS V2 lấy gần nguyên trung bình Chủ nhật trong dữ liệu tham chiếu (~2.300 bánh/ngày ở quy mô ×10), trong khi các ngày thường khoảng 650–900. Biến động ngẫu nhiên theo ngày rất nhỏ, nên đồ thị lặp các đỉnh Chủ nhật ~2.400 bánh. Baseline Rolling-7 cũ còn lấy doanh số của những ngày hết hàng làm nhu cầu, khiến lượng chuẩn bị bị kéo xuống và phép so sánh thiếu công bằng. Cả hai nhánh đã dùng ×10, nhưng cách chọn mốc nhu cầu của Rolling-7 bị lệch khi hết hàng.

POS V3 lấy mốc cùng thứ từ dữ liệu quá khứ đã ×10, giới hạn đỉnh cuối tuần theo mức ngày thường và thêm biến động qua ngày. Trong lượt chạy này, **nhu cầu nền 623–1.187 bánh/ngày**, JOINT bán **640–1.185 bánh/ngày**. Đây là **giả định kịch bản** để mô phỏng AEON hợp lý hơn, chưa phải đo lường POS AEON. Hai nhánh vẫn nhận cùng ngữ cảnh thị trường và cùng nhu cầu nền từng SKU/ngày; script đối chiếu kiểm tra từng cặp trước khi tính hiệu quả.

## Điều chỉnh và mức học theo ngày

M2 dùng dự báo lượng cả ngày làm **trần được duyệt**, rồi đặt mẻ bổ sung theo lượng bán đã quan sát. Ngày thường, vì phần lớn khách đến sau 17:00, dự phóng mẻ 17:00 có sàn bằng 86% mốc sáng; ngày cuối tuần 80%. Điều này giảm việc suy từ một buổi sáng vắng khách thành cả ngày vắng khách, đồng thời vẫn hủy mẻ chưa cần. M1 xét giá lúc 19:30, 20:00, 20:30, 21:00 và 21:30, so lợi ích cứu bánh với hụt giá trên bánh vốn vẫn bán được và ước tính khả năng còn hàng lúc 21:30. M1 không có điểm quyết định 19:00 trong bundle hiện tại.

JOINT dùng kết quả ca đã chốt trước đó ở **61/62 ngày** để cập nhật hệ số hiệu chỉnh, với hệ số từng SKU trong khoảng **0,929–1,037**. Trọng số GBDT không tự train lại mỗi đêm. Sai lệch lượng chuẩn bị so với nhu cầu nền bình quân là **62,77 bánh/ngày** tháng 7 và **55,71 bánh/ngày** tháng 8; hai nửa tháng 7 là **49,25 → 77,20**, hai nửa tháng 8 **51,69 → 60,00**. Các chuỗi này **không chứng minh cải thiện đều đặn từng ngày**. Tác dụng đã xác nhận là so với baseline trong kịch bản 62 ngày này.

## Giới hạn và tái lập

Tháng 7–8 từng được xem trong quá trình chỉnh POS và chính sách vận hành. Vì vậy đây là **thử nghiệm phát triển sau test**, không phải phép kiểm chứng mù ngoài mẫu. Chưa có POS AEON thật để xác nhận mức hủy, lost sales hay lãi thực tế. Thời tiết dùng Open-Meteo JMA GSM Previous Runs tại độ trễ cố định 24 giờ; API không cho xác minh giờ phát hành chính xác của từng bản chạy năm 2022, nên `issued_at=null` và chỉ dùng cho mô phỏng.

- Chạy JOINT: `py -X utf8 scripts/run_test_period.py --branch joint --tag v3full2`
- Chạy baseline: `py -X utf8 scripts/run_test_period.py --branch seasonal --tag v3full`
- Kiểm tra cổng: `py -X utf8 scripts/evaluate_test_period_v3.py`

Mỗi nhánh dùng database riêng trong `runtime/`; script không ghi đè database đã có. Xem [dòng JOINT từng ngày](JOINT_TWO_MONTH_JOINT_V3FULL2.json), [dòng baseline từng ngày](JOINT_TWO_MONTH_SEASONAL_V3FULL.json) và [tổng hợp/cổng kiểm tra](JOINT_TWO_MONTH_V3_EVALUATION.json). Các lượt V2/Rolling-7 cũ là thử nghiệm đã bị loại, không còn xuất hiện trong Báo cáo hiệu quả của ca mới.
