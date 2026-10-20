# Học từ kết quả thực tế

Mở **Học từ dữ liệu** trong dashboard hoặc `http://127.0.0.1:8000/?view=learning`.

1. Tải mẫu M2 hoặc M1, điền kết quả thực tế rồi nạp CSV, XLSX hoặc ZIP. ZIP nhận `daily_outcomes.csv` và `promo_trials.csv`.
2. Hệ thống kiểm tra toàn bộ trước khi lưu. Bản trùng không được tính thêm; bản xung đột bị từ chối, không tự sửa dữ liệu cũ.
3. Chọn loại và nguồn, bấm **Huấn luyện**. Chưa đủ dữ liệu thì báo rõ, không tạo model giả.
4. Đọc báo cáo ứng viên và các điều kiện đạt. Nếu đạt, bấm **Xem và xác nhận áp dụng**, nhập lý do rồi xác nhận.
5. Chỉ ca tạo sau đó dùng phiên bản mới. Có thể quay về parent bằng nút **Quay về model trước**. Những ca đã tạo vẫn giữ model của chúng.

Để dự báo ngày mới, tải forecast thời tiết của ngày đó qua **Dữ liệu đầu vào**. Nếu không tải thêm lịch sử, ca live tự lấy lịch sử kết quả thực tế đã lưu, chỉ đến trước ngày dự báo. Lịch sử tải kèm vẫn được ưu tiên như đầu vào người dùng chỉ định. Chưa có lịch sử thật phù hợp thì cần nạp lịch sử trước; không tự tạo thời tiết hoặc kết quả bán mới.

Nút **Thử luồng bằng dữ liệu demo** tạo dữ liệu tổng hợp tách biệt và huấn luyện LightGBM thật để xem quy trình. Dữ liệu cố ý đơn giản nên sai số demo thấp không chứng minh chất lượng thực tế. Backend cấm áp dụng ứng viên demo, kể cả gọi API trực tiếp. Không tự đưa dữ liệu demo thành dữ liệu thật.

## Dữ liệu M2

Mỗi dòng là một ngày và một SKU. Hiện hỗ trợ 8 SKU V9 đã có; SKU mới cần quy trình thiết kế đặc trưng và kiểm tra riêng.

| Cột | Ý nghĩa |
|---|---|
| date | Ngày ISO YYYY-MM-DD đã kết thúc |
| sku_code | Mã SKU trong danh mục |
| prepared_qty | Sản lượng thực tế đã chuẩn bị |
| sold_qty | Tổng số chiếc đã bán |
| waste_qty | Số chiếc còn lại, được ghi hủy cuối ngày; prepared = sold + waste |
| stockout | 1 nếu từng hết hàng, 0 nếu không; lượng bán không đại diện đầy đủ nhu cầu khi hết hàng |
| discounted_qty | Số chiếc bán ở giá giảm, không vượt sold_qty |
| forecast_rain_mm_previous_day1 | Forecast lượng mưa, không dùng thời tiết quan sát sau ngày bán |
| forecast_temperature_max_c_previous_day1 | Forecast nhiệt độ cao nhất |
| is_public_holiday | 0/1 |
| is_festival_non_public | 0/1 |
| issued_at | Thời điểm phát hành forecast có múi giờ, không sau 06:00 ngày dự báo |

Tối thiểu 63 ngày liên tục, đủ 8 SKU mỗi ngày. 35 ngày đầu tạo lịch sử lag, 14 ngày tiếp theo trở lên để fit, 7 ngày hiệu chỉnh buffer, 7 ngày kiểm tra cuối cùng. Train cần ≥10 dòng hợp lệ/SKU; hiệu chỉnh và kiểm tra cần ≥5 dòng hợp lệ/SKU mỗi phần.

Ngày từng hết hàng, bán hết toàn bộ số chuẩn bị hoặc có bán giảm giá không được làm nhãn nhu cầu cơ sở. Chúng vẫn được giữ để xây lịch sử bán, phù hợp đặc trưng V9. Đây là phương án thận trọng để không coi nhu cầu bị thiếu hàng là nhu cầu thật hoặc cộng uplift khuyến mãi hai lần. Vì vậy, đủ 63 ngày lịch chưa chắc đủ nhãn hợp lệ. Dữ liệu cửa hàng thường xuyên giảm giá cần thêm thiết kế đo nhu cầu cơ sở; hệ thống không tự bịa nhãn cho phần chưa quan sát.

Ca live đã chốt tại 22:00 tự thu các số trên từ sổ giao dịch, tồn và thời tiết, kể cả ca vừa chốt trong ngày hiện tại. Ca mô phỏng không tự được đưa vào tập thật. Thiếu timestamp forecast hoặc có lỗi ghi nhận thì chốt sổ vẫn thành công, nhưng trả cảnh báo và ghi audit lý do chưa thu được. File upload lịch sử chỉ nhận ngày đã qua; dữ liệu tương lai không được học.

## Dữ liệu M1

M1 tiếp tục học **lượng mua tăng thêm do giảm giá**, không đổi sang học tổng số bán rồi giả làm uplift.

Ngoài date, sku_code và các cột thời tiết như M2, cần:

- `slot`: 0, 1, 2, 3, 4 tương ứng 19:30, 20:00, 20:30, 21:00, 21:30.
- `discount_pct`: một bậc hợp lệ trong policy tại slot đó.
- `incremental_promo_qty`: lượng mua tăng thêm đo được, hữu hạn và không âm; bậc 0 phải bằng 0.
- `measurement_method`: phải là `controlled_increment`.
- `experiment_id`: tham chiếu đến phép đo có đối chứng. Người cung cấp chịu trách nhiệm phép đo; ứng dụng không xác minh thiết kế thí nghiệm chỉ bằng tên cột.

Tối thiểu 42 ngày; 28 ngày train trở lên, 7 ngày hiệu chỉnh, 7 ngày test. Mỗi phần phải đủ SKU, slot và bậc giảm hợp lệ. Không đủ độ phủ thì giữ M1 hiện tại. M1 cập nhật cả trọng số LightGBM và empirical response từ phần train, giữ blend 35%/65% và monotonic như policy gốc. Phần hiệu chỉnh được giữ riêng cho báo cáo/split; không dùng nhãn test để fit. Offline uplift MAE tốt hơn chưa chứng minh lịch giá mới tăng lợi nhuận; cần thử nghiệm vận hành sau này.

## Đánh giá và quản lý phiên bản

- Chia theo ngày, không random. Đặc trưng chỉ đọc lịch sử trước ngày được dự báo. Báo cáo test là rolling day-ahead: kết quả thực tế hôm trước được dùng cho dự báo hôm sau, không phải dự báo đồng thời 7 ngày khi chưa có các quan sát đó.
- M2 dùng regression L1 160 cây boosting, seed 42, tham số cố định. Không dò nhiều cấu hình trên test. Buffer q=0,85 tính từ residual của phần hiệu chỉnh, riêng từng SKU. Giữ policy mẻ 4 và sàn 90% baseline.
- Test so sánh ứng viên, incumbent và baseline đơn giản: lag 7 ngày cho M2; empirical response incumbent cho M1.
- Điều kiện: MAE tốt hơn incumbent ít nhất 5%; không kém baseline; mỗi SKU không tệ hơn incumbent quá 10% cộng 0,5 chiếc. M2 kiểm tra thêm pinball loss của sản lượng thực đề xuất không tăng quá 5% cộng 0,1.
- MAE/WAPE tính trên cùng test; WAPE không xác định khi tổng nhãn bằng 0. Không dùng doanh thu mô phỏng để tuyên bố lợi nhuận tăng.
- Không được thử lại cùng holdout để chọn nhiều model. Chạy lại cùng input/parent trả cùng báo cáo; thay dữ liệu cần ít nhất 7 ngày test mới hoàn toàn chưa dùng. Holdout phải sau cutoff của incumbent.
- Model mới lưu hai artifact native, feature schema, SHA-256, parent, fingerprint input, cutoff và báo cáo. Chỉ thay component được huấn luyện; component còn lại được giữ. Không nạp pickle/joblib từ file upload.
- Active pointer cập nhật trong SQLite sau xác nhận và kiểm tra parent còn đúng. Ca đang chạy được ghim phiên bản; cutoff dự báo phải sau dữ liệu cả hai component đã học/đánh giá. Rollback cũng có kiểm tra phiên bản và lý do.
- Dataset, train/evaluate, promote và rollback đều có audit. Không có công cụ Copilot nào được quyền gọi promote/rollback.

## Kiểm chứng

Các kiểm thử dùng database và artifact riêng, không thay model dùng thật. Bao gồm upload CSV/XLSX, đối soát, dữ liệu bị giới hạn tồn, chống trùng/xung đột, huấn luyện cả M1/M2, tách test khỏi trọng số/buffer, checksum, demo không được áp dụng, xác nhận, giữ model ca cũ, lưu active qua restart và rollback. Browser QA thực hiện upload → train → confirm → rollback trên server local riêng và kiểm tra layout mobile.

Thư viện huấn luyện: [LightGBM train](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.train.html). Ollama/Gemini không được fine-tune trong luồng này; phần học mới nằm trong các artifact LightGBM và các thống kê hiệu chỉnh có nguồn dữ liệu rõ ràng.
