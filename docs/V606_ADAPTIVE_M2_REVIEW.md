# Kiểm tra M2 và sửa kế hoạch cố định — 23/10/2026

## Kết luận

Bốn ca 01–04/07 lưu trong prototype đều chuẩn bị 980 bánh vì **policy v3 triệt tiêu thay đổi của dự báo**. Raw forecast có thay đổi, nhưng mức nền lấy từ trung bình public seed cố định; model chỉ được điều chỉnh trong ±0,25√mean, sau đó làm tròn mẻ 4. Đây là lỗi tích hợp kế hoạch. Không thể sửa bằng cách tăng số vòng train đơn thuần.

Lịch sử ca thực sự được cập nhật, nhưng số bán mô phỏng 4× đang đi vào feature của model train ở thang gốc. Từ 02/07 cũng thiếu thời tiết; imputer điền median và cờ OOD bật. Adapter trả nhãn fallback nhưng policy v3 vẫn dùng raw forecast. Cả ba điểm đã được sửa cho phiên bản `V606-frozen-prototype-adaptive-v4`.

## Huấn luyện đối chứng đã chạy

Chỉ đọc ZIP 02 `02_TRAIN_VALIDATION`, kiểm tra checksum mọi tệp. Fit 777 SKU-ngày Jan–Apr; validation 420 SKU-ngày May–Jun. Join target theo date/SKU, chọn riêng horizon `day` hoặc `to_2130`. X chỉ gồm allowlist; nhãn, kết quả cuối ngày và action không vào X. Không đọc private/SQLite/POS tháng 7–8 trong script train.

Đã thử **64 cấu hình** (32 mỗi horizon), gồm độ sâu, số vòng, learning rate và mức phạt dự báo thiếu. Ngừng ở ngân sách này, không train vô hạn trên cùng validation.

| Validation `day` | Model gốc tái lập | Ứng viên có loss thấp nhất |
|---|---:|---:|
| Censor-aware loss | 44,8085 | 42,3855 |
| MAE trên dòng không censored | 6,4820 | 5,6457 |
| Tỷ lệ dự báo dưới mức bán tối thiểu ở dòng censored | 66,47% | 86,83% |

Tỷ lệ cuối **không phải xác suất hết hàng**. Nó cho biết dự báo còn thấp hơn lượng bán đã biết ở các dòng mà nhu cầu thật có thể cao hơn nữa. Ứng viên giảm MAE nhưng kém hơn ở kiểm tra này, nên **không được thay model đang dùng**. Không có cấu hình nào đồng thời giảm censor-aware loss, không tăng MAE và không tăng tỷ lệ dự báo thiếu so với bản gốc. Kết quả từng cấu hình, checksum nguồn và gate nằm tại `v606/V606_M2_retrained_20261023/training_report.json`.

Artifact ứng viên và bản refit Jan–Jun chỉ là tài sản phát triển, không được loader vận hành nạp. Chín tệp model gốc vẫn nguyên byte so với ZIP người dùng cung cấp. M1 giữ nguyên: model bắt chước hành động đã ghi nhận, chưa có bằng chứng causal uplift để huấn luyện tối ưu giảm giá sớm.

Permutation diagnostic của ứng viên cho thấy ảnh hưởng thời tiết yếu; chưa chứng minh thêm thời tiết cải thiện dự báo validation. Không báo cáo model đã học đúng quan hệ thời tiết–nhu cầu AEON. Bảy SKU vốn được phân bổ từ proxy, không phải POS AEON thực.

## Policy v4 dùng gì?

- Khi dựng feature model: chỉ số bán/chuẩn bị của ca mô phỏng busy4 đã chốt được chia đúng hệ số 4. Seed đã ở thang train nên không chia lần nữa. Sổ bán, doanh thu và tồn hiển thị giữ nguyên đơn vị POS.
- Khi tính kế hoạch: kết hợp model quy đổi về tải khách và tối đa 7 ngày bán thực đã ghi nhận của chính SKU/nhánh; trọng số tăng theo số ngày quan sát, không còn cắt thay đổi vào dải nhỏ cố định. OOD thật sự chuyển sang lịch sử, không chỉ gắn nhãn fallback.
- Ngày vừa hết hàng là lower bound; không coi lượng bán đó là toàn bộ nhu cầu. Kế hoạch có đệm dựa trên √kỳ vọng và biến động bán quan sát, reserve 4, làm tròn mẻ và kiểm tra công suất giả định.
- Tồn dự kiến 21:30 dùng tỷ trọng bán trước mốc này từ POS các ngày đã chốt. Chưa đủ dữ liệu thì tỷ trọng 92,5% là giả định từ kịch bản 75% sau 17h. Hiển thị riêng ước tính với tồn thực ghi nhận lúc 21:30. **Không cam kết mọi SKU luôn còn hàng.**
- Lag/rolling cập nhật mỗi ngày; trọng số XGBoost không tự fit lại từ dữ liệu test. Đây là cập nhật đầu vào/policy, không phải online weight training.

Vòng phát triển 4 ngày seed 42 cho chuẩn bị **1.008 → 1.020 → 1.060 → 1.004**. Tồn nhỏ nhất trong bảy SKU lúc 21:30 lần lượt 17, 8, 20, 13 chiếc; không có lượt mua bị mất trong bốn ngày này. Tồn cuối ngày 185, 229, 243, 194 chiếc: **chưa chứng minh giảm tồn so với policy cũ**. Xem `V606_ADAPTIVE_DEVELOPMENT_LOOP.json`. Đây là kiểm tra vòng lặp, không phải bằng chứng lợi nhuận hoặc holdout mới. Thị trường khách và RNG được giữ nguyên; không chỉnh simulator để làm policy thắng.

## Thời tiết

Bổ sung snapshot public ngày trước cho kỳ demo từ [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), theo tọa độ gốc trong BUILD_METHOD: 10.8016, 106.6174; grid trả về 10.790861, 106.6313. Lưu URL, ngày tải, múi giờ và ngày tham chiếu trong `v606/public_context/prior_weather_development.json`. Không thay bản seed thời tiết gốc.

Runtime chỉ lấy đúng ngày D−1, không lấy actual thời tiết ngày D. Đây vẫn là **reanalysis hậu nghiệm phục vụ phát triển mô phỏng**, không phải forecast đã được xác nhận có sẵn lúc 06:00 năm 2022. Không bịa `issued_at`. Đường vận hành thật từ chối dùng context reanalysis demo này. Muốn kiểm chứng thời tiết như hệ thống thực cần forecast đúng vintage và POS thực.

## Tiếp tục ca đang chạy

Nhấn Ctrl+F5. Trong Báo cáo hiệu quả, **Chốt ca** khi đã đến 22:00, rồi **Tạo kế hoạch ngày kế tiếp**. Kế hoạch mới dùng chính lịch sử nhánh đã chọn, không bị ca chạy lại khác đè lên. Ca cũ vẫn ghim engine v3, số lượng chuẩn bị/giao dịch không sửa hồi tố. Báo cáo giữ lịch sử qua thay đổi policy nếu cùng trọng số model và cùng thị trường/seed; bảng ngày có ghi phiên bản.

Tháng 7–8 đã được xem trong quá trình debug: không gọi vòng hiện tại là một test mù mới. Một đánh giá độc lập cần kỳ dữ liệu chưa dùng phát triển.
