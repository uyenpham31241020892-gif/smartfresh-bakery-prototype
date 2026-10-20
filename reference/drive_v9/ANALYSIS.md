# Phân tích kết quả SmartFresh V9

Mã lần chạy: `d8b621a5bff64203a32d79ed790dadd2`. Kỳ đánh giá: 2022-09-01 đến 2022-09-30.

## Kết quả

| Chỉ tiêu | BASELINE | M1_M2_SELECTED |
|---|---:|---:|
| Chuẩn bị | 9,492 | 9,176 |
| Bán | 6,810 | 6,957 |
| Tồn cuối ngày | 2,682 | 2,219 |
| Nhu cầu không đáp ứng | 34 | 54 |
| Doanh thu VND | 105,249,380 | 106,158,050 |
| Chi phí giả định VND | 67,073,760 | 65,110,140 |
| Contribution trước overhead VND | 38,175,620 | 41,047,910 |

Doanh thu thay đổi +0.8633%; tồn cuối ngày giảm 17.2632%; lượt nhu cầu không đáp ứng thay đổi +20. Đây là các tác động cần xem đồng thời, không suy ra hiệu quả chỉ từ một KPI.

M2 WAPE: 11.9532%. M2 MAE: 3.3414. Lịch sử feature của model chỉ được cập nhật bằng doanh số quan sát sau khi chốt ngày; điểm số được tính sau quyết định.

## Đối soát

480 SKU-ngày đạt 4 kiểm tra stock, số giao dịch, doanh thu ledger và chi phí. Cả 6 kiểm tra ràng buộc vận hành đạt PASS. `EXECUTION_TRACE.csv` xác nhận thứ tự dự báo, 5 slot và chốt ngày. Hash model/config được chốt trước dự báo và không thay đổi trong lần chạy.

## Phạm vi diễn giải

Demand và price response là dữ liệu giả lập. Chi phí là giả định 45% giá niêm yết, contribution chưa trừ overhead. Không chọn lại cấu hình từ kết quả kỳ đánh giá; chỉ so BASELINE với cấu hình tháng 8 đã chốt.
