# JOINT là cấu hình vận hành chính

Cập nhật 05/11/2026. Ca mới, gồm POS tự động và nhập tệp, dùng
`SMARTFRESH_V4_JOINT_V2`. Ô chọn nguồn ×1/×10 đã bỏ. Baseline, công suất,
lịch sử mẫu và lượt mua tự động dùng quy mô ×10; không nhân giá đơn vị,
phần trăm giảm hoặc dữ liệu POS người dùng nhập thêm lần nữa.

## Adapter và bundle thực sự được nạp

- Nguồn được nâng cấp trực tiếp: `TRAINED_TESTED/agent_sandbox/smartfresh_adapter.py`.
- Chính sách JOINT: `services/joint_policy.py`; bundle đã train lại: `models/joint/`.
- Adapter cũng mặc định nạp thư mục này khi được import trực tiếp.
- `models/joint/manifest.json` lưu SHA256 nguồn adapter, chính sách, tập fit,
  pipeline và bundle. Runtime kiểm tra hash và metadata phiên bản trước khi dùng.
- File tham chiếu trên Desktop không bị sửa. Adapter trong dự án nay khác file
  Desktop vì đã bổ sung JOINT theo yêu cầu này.
- V4 cũ và bản thử ×10 trước được giữ để đọc ca lịch sử, không còn là lựa chọn
  tạo ca mới. Ca đang mở cũ giữ phiên bản đã ghim; tạo **Ca mới** để thử bản này.

## Vì sao trước đây thường không có giảm giá

M1 trước học nhãn lượng bán theo nhịp cũ, trong khi luồng khách runtime đã được
dời giờ và tăng quy mô. Mức tăng lượng bán mà model dự báo khi giảm giá thấp,
nên lợi ích ròng so với HOLD âm. Bằng chứng trước sửa nằm trong
`JOINT_BEFORE_PRICING.json`; ví dụ DN-004 lúc 21:30 còn 134 bánh, model dự báo
khoảng 18,5 bánh nếu giữ giá và 22,6 bánh nếu giảm 50%, nên giảm sâu không có lợi.
Không khắc phục bằng cách ép luôn có khuyến mãi.

M1 nay được train lại bằng các thử nghiệm giá ghép cặp trên luồng POS mô phỏng
cùng quy tắc đến quầy/phản ứng giá với runtime. Đã sửa việc đếm lần đề xuất:
chỉ lần **áp dụng đổi giá** mới dùng hạn mức, từ chối/làm mới không dùng hạn mức.

## M2

HGBDT được train riêng với quantile loss ở Q10/Q25/Q45/Q50/Q75/Q90. Dùng các
phân vị thật, sắp xếp lại khi dự báo giao nhau, không tạo Q75/Q90 bằng cách nhân Q50.

Chính sách kinh doanh chọn dải Q45–Q50 từ thứ Hai–Năm, Q75–Q90 từ thứ Sáu–CN
và ngày lễ. Tỷ số `Cu/(Cu+Co)`, với `Cu=giá bán−giá vốn`, `Co=giá vốn+phí hủy`,
chọn vị trí trong dải; đây là ràng buộc theo thứ, không phải tối ưu Newsvendor
không ràng buộc. Thứ Ba/Tư không quá Q47,5; Crepe/Red Velvet Q45 giữa tuần.

Làm tròn mẻ 4, giới hạn công suất. Lượng duyệt sáng là trần; mẻ 14:00/17:00
được đặt có điều kiện theo POS đã quan sát lúc 12:00/15:00. Ngày thường giữ
sàn dự phóng buổi tối vì phần lớn nhu cầu đến sau 17:00. Mẻ không đặt được
hủy khỏi kế hoạch, không tính thành bánh đã chuẩn bị hay bánh hủy cuối ca.
Đợt bổ sung chưa nhận không nằm trong tồn khả dụng.

Doanh số ngày hết hàng chỉ là cận dưới nhu cầu. 2.887 dòng censored dùng ước
lượng Q75 từ tập không censored, giữ ít nhất doanh số quan sát, trọng số 0,5.
Đây là imputation có giả định; quantile loss tự nó không xác định được nhu cầu
thật bị mất. Join nhãn chỉ lấy `target_horizon=day`.

## M1

- Xét 19:30, 20:00, 20:30, 21:00 và 21:30. Trước 19:30 không đề xuất markdown.
- Dự báo bán từng khoảng 30 phút tới 22:00 từ trạng thái đã quan sát, kết hợp
  tối đa 7 ca trước cùng nhóm ngày và cùng giá; không coi cửa sổ hết hàng hay
  khác giá là doanh số bằng 0 ở giá hiện tại.
- HOLD nếu xác suất tự bán hết ở giá niêm yết hoặc giá hiện hành ≥88%.
- Trước 21:30, giữ xác suất còn hàng lúc 21:30 ≥80%; mỗi bước tăng mức giảm
  không quá 10 điểm phần trăm, trần theo mốc là 20/25/35/40%.
- Lúc 21:30 được xét tới 50%, chỉ khi lợi ích ròng vượt 500đ. Không ép giảm sâu
  nếu món bán tốt hoặc phần bánh cứu thêm không bù phần bán hớ.
- Lợi ích = bánh cứu thêm × (giá sau giảm + phí hủy tránh được) − hụt giá trên
  bánh vốn vẫn bán được − phí đổi giá. Không trừ giá vốn đã sản xuất lần thứ hai.
- Phí theo kênh: tem 350đ/lần, E-ink 0đ/lần trong cấu hình mẫu. Tối đa 3 lần
  đổi/SKU/ngày, cách nhau ít nhất 30 phút; AI giữ lượt cuối cho 21:30.
- Mỗi dòng bằng chứng có xác suất, ứng viên, net gain và lý do HOLD/đổi giá.

80% ở đây là **xác suất còn hàng**, không phải phải giữ 80% số bánh ban đầu.
Xác suất sử dụng giả định đếm Poisson với kỳ vọng từ model; chưa được hiệu
chuẩn trên POS thật AEON. Không coi 88% là độ tin cậy đã được đo tại cửa hàng.

## JOINT và lịch sử sáng hôm sau

Khi chốt ca, đối chiếu dự báo M1 ở giá gốc và giá thực áp dụng để ước lượng
phần bán tăng thêm do khuyến mãi trong từng cửa sổ. Lưu `incremental_promo_qty_estimated`
và doanh số tự nhiên ước tính, vẫn giữ nguyên sổ giao dịch gốc.

`prepare` khử phần tăng thêm này khỏi `sold_calendar_lag1`, lag7 và
`sold_last7_observed_mean`. Không trừ tất cả bánh bán giảm giá: bán 20, trong đó
12 bán giảm giá nhưng chỉ 6 là tăng thêm, thì lịch sử tự nhiên là 14.
Chỉ dùng ngày đã chốt trước ngày dự báo; không dùng oracle khách tương lai.
Ca mới dùng lịch sử nhánh đã chốt; dữ liệu nhập có thể mang cùng cột ước lượng.

## Dữ liệu, chất lượng và cách kiểm tra

| Model | Dòng fit | Dòng validation | MAE validation | MAE trung bình SKU từ fit |
| --- | ---: | ---: | ---: | ---: |
| M2 | 11.655 | 420 | 50,273 bánh | 70,847 bánh |
| M1 | 51.819 | 28.014 | 3,351 bánh/30 phút | 8,797 bánh/30 phút |

Fit đến 30/04/2022; validation hồi cứu 01/05–30/06/2022. M1 có 111 ngày fit
độc lập và 60 ngày validation; nhiều dòng phản thực cùng ngày không phải khách
hay ngày quan sát độc lập. Đây là bằng chứng trên dữ liệu mô phỏng, chưa chứng
minh tăng doanh thu, giảm hủy hay triệt tiêu lost sales tại AEON. Trọng số
GBDT không train lại bằng tháng 7–8. Chính sách vận hành và POS V3 đã được
điều chỉnh sau khi xem kết quả mô phỏng tháng 7–8; vì vậy đây là **thử nghiệm
phát triển sau test**, không phải đánh giá mù ngoài mẫu.

Nhịp khách ngày thường tăng mạnh sau 17:00; cuối tuần/lễ có khách cả ngày và
đông buổi tối. POS V3 lấy mốc từ lịch sử đã ×10, giới hạn đỉnh cuối tuần theo
giả định và thêm biến động giữa ngày; seed cố định cho cùng hai nhánh so sánh.
Ca mới đóng tự lưu nhãn POS cho vòng học tiếp theo; không tự thay trọng số giữa ca.

```text
python scripts/train_volume_models.py
python -m pytest tests/test_joint_policy.py tests/test_volume_scenario.py tests/test_v4.py tests/test_checkpoint_review.py tests/test_m1_contract.py tests/test_providers.py -q
python scripts/check_joint_day.py
python scripts/check_volume_ui.py
```

`JOINT_AFTER_PRICING.json` ghi đầy đủ bốn ca thứ Hai, thứ Ba, thứ Sáu và thứ Bảy;
`JOINT_BROWSER_QA.json` ghi kiểm tra Edge desktop/mobile, tab sáng/tối, chỉ hiện
món đổi giá và chỉnh thủ công. Các script dùng DB tạm, không sửa ca của người dùng.
`JOINT_QA_RESULTS.json` và `JOINT_pytest.xml` là kết quả kiểm thử bản bàn giao.

Toàn bộ test lịch sử chưa sạch: ba lỗi import cũ ở `test_day_loop.py`,
`test_learning.py`, `test_evaluation_gd8.py` tham chiếu API đã bị bỏ từ V4.
`tests/test_workflow.py` còn ba kỳ vọng từ luồng cũ (SKU `BK-001`, weather live
không có vintage đã xác minh và hard floor khi từ chối giá). Chín test trong
`test_workflow.py` + `test_weather_api.py` chạy được sáu; ba kỳ vọng cũ này
không qua. Không coi những test đó là đã pass.
