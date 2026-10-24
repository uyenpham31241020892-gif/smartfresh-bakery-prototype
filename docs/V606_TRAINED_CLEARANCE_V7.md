# M1 v7: dự báo sức bán còn lại và thử mức giảm có điều kiện

Thay thế hành vi v6 luôn HOLD vì chưa có uplift đã xác minh. Chỉ ca mô phỏng mới dùng
thị trường phản ứng giá giả định v7; ca cũ, giao dịch, tồn và mức giá đã áp dụng giữ nguyên.
Ca vận hành thật không được mở khóa giảm bằng bằng chứng mô phỏng.

## Đã train gì

`scripts/retrain_v606_m1.py` kiểm tra SHA256 của ZIP 02 trước khi học. Fit 3.885 checkpoint
02/01–30/04/2022; chọn cấu hình trên 2.100 checkpoint 01/05–30/06/2022.
Không đọc ZIP 01/private, runtime/test tháng 7–8, hay dữ liệu ca mô phỏng để fit.
Giữ nguyên toàn bộ artifact gốc. Artifact mới: `v606/V606_M1_remaining_v7`.

Hai XGBoost dự báo bán quan sát còn lại đến 22:00 và trước 21:30. Cả hai chọn depth 3,
60 rounds, từ bốn cấu hình mỗi horizon. Feature đúng allowlist M1 pre-action; tổng bán
các khoảng tương lai chỉ là LABEL, kiểm tra available_at > decision_at. Khoảng hết hàng
được coi là lower bound, không coi bán bị kiểm duyệt là toàn bộ nhu cầu.

| Horizon | Censor-aware squared loss validation | Baseline ngoại suy tốc độ bán | MAE trên nhãn không censored |
|---|---:|---:|---:|
| Đến 22:00 | 6,512 | 25,713 | 2,402 chiếc |
| Đến 21:30 | 4,188 | 18,818 | 1,656 chiếc |

Đây là thang dữ liệu train, chưa nhân hệ số mô phỏng 4x. Model vẫn dự báo dưới đường
hành động lịch sử; không phải ước lượng nhu cầu tiềm ẩn hoặc hiệu ứng nhân quả giá.
Validation dùng chọn model và phát triển policy, không phải kết quả test độc lập.

## Cách chọn giá

Từ 19:30 đánh giá từng SKU ở checkpoint và khi làm mới. Không bắt buộc giảm lúc 19:30.
Dùng dự báo còn lại kết hợp tốc độ bán 30/60 phút. Khi dự kiến dư vượt max(4 chiếc,
5% lượng chuẩn bị), xét 10/20/30/40%; không lặp các bước 5% mặc định.
Trần trước 20:30 là 20%, trước 21:30 là 30%, sau đó 40%; trần không phải mức bắt buộc.

Mỗi phương án phải giữ tồn cho lượng bán dự kiến đến 21:30 sau phản ứng giá, cộng đệm
1,64 × căn lượng bán đó + 4 chiếc. Đệm là heuristic mô phỏng, không bảo đảm không hết hàng.
Ưu tiên phương án doanh thu tăng giả định; từ 21:00 cho phép bán thêm ít nhất hai chiếc
với doanh thu giả định không giảm, để xử lý tồn. Chi phí chuẩn bị đã phát sinh không trừ lần hai.
Không có phương án phù hợp thì HOLD và đánh giá tiếp, không yêu cầu quản lý duyệt HOLD.
Giá đổi chỉ áp dụng sau quản lý duyệt, không sửa hóa đơn cũ.

Mức giảm do bộ tối ưu kịch bản chọn; **chưa train được độ co giãn hoặc mức giảm tối ưu
từ bằng chứng nhân quả**. Dữ liệu lịch sử không có thử nghiệm giá đủ để suy ra điều đó.
Kịch bản v7 khai báo số lượt mua thêm kỳ vọng = lượt mua gốc × 2 × tỷ lệ giảm giá.
Ví dụ 20% tương ứng tăng 40% lượt mua trong khoảng được giảm, theo GIẢ ĐỊNH này.
Lượt mua gốc giữ đúng RNG cũ, nhóm nhạy giá sinh bằng RNG riêng, cố định trước khi
biết model/giá. Model/AI không đọc dòng khách tương lai, draw, hidden demand hoặc nhãn test.

UI và Copilot hiển thị phần dư dự kiến, mức giảm, số bán thêm giả định, số bán thêm
cần để hòa vốn và thiệt doanh thu nếu khách không phản ứng. Gate ghi
`SIMULATION_ASSUMED_CLEARANCE_BENEFIT`, không giả thành `VERIFIED_POSITIVE_BENEFIT`.
Manager có thể giữ giá; thay mức khác cần được đánh giá lại, không mặc nhiên dùng
lợi ích của mức đã chấm cho mức chưa chấm.

## Kiểm tra độ nhạy, không chứng minh hiệu quả AEON

`scripts/evaluate_v606_clearance.py`: lịch validation 60 ngày, seed 607, tải khách chỉ
từ trung bình FIT Jan–Apr. Cùng lượng chuẩn bị và cùng dòng yêu cầu tiềm năng cho
HOLD và policy; duyệt ngay chỉ là giả định của đánh giá offline.

| Phản ứng thực trong mô phỏng | Thay đổi doanh thu so HOLD | Thay đổi tồn cuối ca |
|---|---:|---:|
| Không phản ứng, hệ số 0 | −7,36% | 0 chiếc |
| Phản ứng yếu, hệ số 1 | −1,67% | −2.929 chiếc |
| Theo giả định policy, hệ số 2 | +3,48% | −5.455 chiếc |

Tổng trên 60 ngày, không phải mỗi ngày. Đệm bất định được bổ sung sau khi đánh giá phát
triển trước đó phát hiện bốn ngày hết hàng sớm; **validation đã được dùng lại để sửa policy**.
Sau sửa, cả ba kịch bản ghi nhận 0/60 ngày hết hàng trước 21:30 trong lần kiểm tra này.
Vẫn có yêu cầu không phục vụ được sau 21:30, đặc biệt khi phản ứng mạnh; không che chỉ số này.
Không dùng kết quả này làm cam kết lợi nhuận, chứng minh tác động hoặc test chính thức.

Chạy lại bằng Python của repo với `--source` trỏ bản giải nén ZIP 02 bên ngoài runtime.
Nguồn, artifact, kết quả cấu hình và sensitivity được lưu trong hai report JSON cùng thư mục model mới.
