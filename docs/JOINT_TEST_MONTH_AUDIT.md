# Đánh giá vận hành tháng 07/2022

> Bản đối chiếu tháng 7 trước khi hoàn tất chạy hai tháng. Bản hiện hành và lịch sử đã chốt nằm tại [Đánh giá 07–08/2022](JOINT_TWO_MONTH_AUDIT.md). Số liệu của bản này không còn được hiển thị như báo cáo hiện hành trong ứng dụng.

Chạy `py -X utf8 scripts/audit_joint_test_month.py`. Đây là 31 ngày liên tục **01–31/07/2022**, thuộc giai đoạn đánh giá sau validation của bộ V4. Hai nhánh vận hành độc lập trên cùng seed 42, cùng bộ sinh POS V2 và cùng dữ liệu thời tiết. Nhu cầu nền tổng và từng SKU được kiểm tra khớp giữa hai nhánh trước khi công bố.

| Nhánh | Chuẩn bị | Bán | Bán/chuẩn bị | Tồn | SKU-ngày hết hàng | Lãi góp mô phỏng | Sai lệch chuẩn bị với nhu cầu nền/ngày |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| JOINT | 42.564 | 37.969 | 89,2% | 4.595 | 46 | 451.203.157 ₫ | 165,7 bánh |
| Baseline Rolling-7 | 25.132 | 23.892 | 95,1% | 1.240 | 143 | 313.311.247 ₫ | 473,7 bánh |

JOINT bán nhiều hơn **14.077 bánh** và lãi góp mô phỏng cao hơn **137.891.910 ₫** so với Rolling-7; đồng thời tồn nhiều hơn **3.355 bánh**. Baseline có tỷ lệ bán/chuẩn bị cao nhưng hết hàng nhiều, nên không thể dùng riêng tỷ lệ đó để kết luận baseline tốt hơn. Lãi góp dùng giá vốn và phí hủy/markdown giả định của prototype; không phải lợi nhuận AEON.

| Giai đoạn JOINT | Sai lệch chuẩn bị với nhu cầu nền/ngày | SKU-ngày hết hàng | Bán/chuẩn bị |
| --- | ---: | ---: | ---: |
| 16 ngày đầu | 167,4 bánh | 20 | 88,5% |
| 15 ngày cuối | 163,9 bánh | 26 | 90,0% |

Sai lệch chuẩn bị gần như đi ngang, còn số SKU-ngày hết hàng tăng; bài kiểm tra này **không chứng minh JOINT ngày càng tối ưu**. Chính sách chống phản hồi sai giúp dự báo không sụp theo doanh số bị giới hạn bởi hết hàng, nhưng vẫn cần đánh giá thêm nhiều tháng, nhiều seed và POS AEON thật. Baseline Rolling-7 xấu đi rõ trong nửa sau: sai lệch tăng **428,8 → 521,6 bánh/ngày**, SKU-ngày hết hàng tăng **68 → 75**.

| Nhánh | Cách chuẩn bị | Cách đổi giá |
| --- | --- | --- |
| JOINT | Quantile M2 và bộ chặn sai lệch theo baseline cùng loại ngày; chỉ cập nhật hệ số từ các ca bán đủ hàng | Chính sách M1 hiện hành, có duyệt |
| Baseline Rolling-7 | Trung bình số bán 7 ngày gần nhất trong chính nhánh đó, làm tròn mẻ 4 và giới hạn công suất; đây là `Engine.baseline` của ứng dụng | Cùng chính sách M1, có duyệt |

POS sinh cơ hội mua theo từng cửa sổ thời gian từ lịch sử trước tháng test, thứ/ngày nghỉ, seed và giá đang áp dụng. Nhu cầu nền không phụ thuộc lượng bánh JOINT hoặc baseline đã chuẩn bị. Khi giá khác nhau, cơ hội mua nhạy giá có thể khác nhau theo đúng kịch bản. [Dữ liệu từng ngày và SKU](JOINT_TEST_MONTH_AUDIT.json) là artifact độc lập; ứng dụng đọc nó trong mục **Báo cáo hiệu quả → Đánh giá vận hành tháng 07/2022** cùng với biểu đồ và bảng bán/tồn hằng ngày. Bài chạy không ghi ca giả vào database người dùng.

Thời tiết được lấy từ [Open-Meteo Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api), model JMA GSM, biến mưa và nhiệt độ ở độ trễ **24 giờ**, cho tọa độ minh họa **10.7769, 106.7009** tại TP.HCM. Đây chưa phải tọa độ chi nhánh AEON đã xác minh. API cung cấp lead time cố định cho 2022 nhưng không có timestamp công bố từng lần chạy; ứng dụng ghi `issued_at=null`, `vintage_verified=false` và chỉ cho phép mô phỏng.

Model JOINT giữ nguyên trọng số trong cả tháng. Bộ chặn đầu ra cập nhật hệ số từ lịch sử bán đủ hàng, nên bảng theo ngày hiển thị số quan sát đủ điều kiện và hệ số hiệu chỉnh. Điều đó cho phép kiểm tra mức thích nghi của chính sách nhưng không chứng minh tái huấn luyện model. POS cũng là kịch bản tổng hợp chưa được hiệu chỉnh bằng giao dịch AEON. Bộ sinh POS và bộ chặn JOINT đều sử dụng nhóm thứ/ngày nghỉ của baseline, nên lợi thế của JOINT trong kịch bản này **không phải xác nhận độc lập** về độ chính xác tại AEON. Chênh lệch lãi góp, doanh số và tồn chỉ có giá trị trong mô phỏng.
