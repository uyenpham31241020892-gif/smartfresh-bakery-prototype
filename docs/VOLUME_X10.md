# Bản thử nghiệm ×10 ngày 04/11/2026 (đã thay thế)

Tài liệu dưới đây lưu trạng thái vòng trước. Từ 05/11/2026, JOINT là cấu hình
vận hành chính cho mọi ca mới; không còn lựa chọn nguồn ×1/×10. Xem
[JOINT_POLICY.md](JOINT_POLICY.md) để biết mô hình và kiểm thử hiện hành.

Ngày cập nhật: 04/11/2026. Kịch bản mặc định cho **ca mô phỏng mới** là
`AEON_VOLUME_X10_V1`; model ghim theo ca là `SMARTFRESH_V4_RETRAIN_X10_V1`.

## Giao diện

- Trước 17:00, hoặc khi còn duyệt kế hoạch: chỉ hiện tab Kế hoạch sản lượng
  trong hai tab quyết định. Từ 17:00 chuyển sang Giảm giá cuối ngày.
- M1 vẫn đánh giá tại 19:30, 20:00, 20:30, 21:00 và 21:30.
- Chỉ món có mức giá thay đổi xuất hiện thành thẻ đề xuất/đã áp dụng.
- Nếu tất cả giữ giá, ghi snapshot `auto_hold` và tiếp tục ca, không giả lập
  thao tác duyệt. Snapshot vẫn lưu đầy đủ SKU để kiểm toán.
- Mục thu gọn **Quản lý chỉnh giá món đang giữ giá** cho phép mở bảng thủ công.
  Chỉnh mức khác đề xuất cần lý do, duyệt rồi áp dụng; kiểm tra vai trò quản lý,
  trần theo giờ, không tăng giá lại, cooldown 30 phút và tối đa hai lần đổi.

## Đúng model và đúng đơn vị

Adapter được người dùng chỉ định:
`TRAINED_TESTED/agent_sandbox/smartfresh_adapter.py`.
File này đã được cập nhật trong workspace trong lúc thực hiện và bản cuối trùng
với `C:/Users/Administrator/OneDrive/Desktop/smartfresh_adapter.py`:

`7e3289e6191df19232c0f49d557e5eb8e00ccab80feadb21d02a4d7b04cc065d`

Không ghi đè bundle frozen ở `v4/artifacts_build/models`. Bundle mới nằm trong
`models/volume_x10`, có metadata, nguồn adapter, nguồn fit, hash từng file và
kết quả validation trong `manifest.json`. Runtime nạp đúng preprocessor từ
adapter chỉ định, kiểm tra hash và scale, không fallback âm thầm sang V9/V4 cũ.
Ca ghim hash khác bundle đang nạp bị chặn tiếp tục để tránh trộn model.

Chạy lại train bằng `python scripts/train_volume_models.py`. Script dùng các
loader và kiến trúc HGBDT của `TRAINED_TESTED/train_v4_original_pipeline.py`,
chỉ đọc phần fit đến 30/04/2022. Sửa lỗi join nhãn M2 trong pipeline nguồn:
chỉ chọn `target_horizon=day`, không trộn nhãn `to_1930`/`to_2130` vào bài toán
dự báo cả ngày.

Các lượng chuẩn bị, bán, tồn, công suất, kệ/kho, tốc độ bán và nhãn lượng bán
được đổi sang đơn vị ×10 cùng nhau. Giá đơn vị, chi phí đơn vị, % giảm, thời gian,
cờ ngày lễ và số phút hết hàng giữ nguyên. Mẻ quản lý nhập vẫn là bội số 4.
M2 tính lại đề xuất bằng model mới nên đề xuất không bắt buộc đúng 10 lần đề xuất
V4 cũ. Baseline lịch sử chuẩn bị/bán/tồn và tổng tiền là đúng 10 lần nguồn;
giá bán trung bình, tỷ lệ giảm, tỷ lệ bán/tồn giữ nguyên.

| Model | Dòng fit | Dòng validation | MAE (bánh) | MAE trung bình SKU từ fit |
| --- | ---: | ---: | ---: | ---: |
| M2 | 11.655 | 420 | 52,666 | 70,847 |
| M1 | 46.620 | 2.100 | 8,426 | 10,120 |

Đây là validation hồi cứu tháng 5–6/2022 trên nhãn nguồn đổi sang ×10, không
phải holdout mù hay bằng chứng tăng lợi nhuận tại AEON. Nhân lượng ×10 không tăng
số ngày quan sát độc lập. Model mới chưa được xác nhận độ chính xác trên nhịp
khách thực tế của quầy bánh. Các model hiện tại train từ dữ liệu fit được đổi
đơn vị; chưa tự retrain từ các ca mô phỏng mới phát sinh.

## Nhịp POS

Worker riêng tạo mười lượt đơn vị cho mỗi lượt nguồn, có event/customer ID riêng.
Tổng organic theo SKU/ngày giữ đúng tỷ lệ ×10; seed thay đổi giờ đến nhưng không
thay tổng. Các món cùng customer ID và replica cùng thời điểm ghé.

Trọng số theo giờ 08:00–21:59 trong `services/volume_scenario.py`:

- Ngày thường: `2,2,3,4,5,4,4,4,5,13,15,15,14,10` — khoảng 67% sau 17:00.
- Cuối tuần/ngày nghỉ lễ: `5,5,6,6,6,6,6,6,6,9,10,11,10,8` — khách xuyên ngày,
  khoảng 48% sau 17:00, cường độ buổi tối cao hơn mỗi giờ ban ngày.
- Cơ hội mua do giảm giá chỉ trong 19:30–22:00, giữ giả định response strength 0,6;
  không phát sinh giao dịch khi chưa áp dụng giá. Không tính khách promo vào
  tổng organic. Cùng seed/giá cho cùng luồng dù chạy đồng hồ theo bước khác nhau.
- Worker chỉ trả cửa sổ đã trôi qua. Oracle tương lai và lượt không phục vụ được
  không đi vào feature/nhãn POS quan sát của model.

Khung siêu thị 08:00–22:00 tham chiếu
[AEON MALL Long Biên](https://aeonmall-long-bien.com.vn/thong-tin-tong-quat/bang-thoi-gian-hoat-dong/).
Trọng số giờ và ×10 là giả định người dùng yêu cầu, không phải phân bố khách AEON
đã đo. [Google Business Profile](https://support.google.com/business/answer/6263531?hl=en)
mô tả độ đông theo giờ là mức tương đối, không cung cấp tổng giao dịch của quầy.

Chốt ca tự thu 7 dòng M2 và cửa sổ M1 có feature/giá nhất quán, đánh dấu censor
và thời điểm có nhãn, lưu riêng nguồn `simulation_x10`. Thu lại cùng ca không
nhân đôi. Các dòng này chuẩn bị cho vòng train mô phỏng tiếp theo; không tự đổi
trọng số và không đưa vào nguồn dữ liệu thật. Ngày tiếp theo dùng kết quả POS
đã chốt trực tiếp, không nhân ×10 lần nữa.

## Tương thích và kiểm tra

Ca cũ giữ nguyên dữ liệu, model và simulator ghim ban đầu. Vẫn có lựa chọn thị
trường V4 gốc và replay POS gốc ×1. Ca live tiếp tục dùng bundle V4 gốc; model ×10
chỉ áp cho mô phỏng. Giám sát, registry, health và restore hiểu phiên bản ×10;
restore kiểm tra hash bundle ghim của ca.

Kiểm tra bằng:

```text
python -m pytest tests/test_volume_scenario.py tests/test_checkpoint_review.py tests/test_v4.py tests/test_m1_contract.py -q
python scripts/check_volume_ui.py
```

Browser QA dùng DB tạm, Edge headless, không thay ca hoặc tài khoản của người dùng.
Kết quả: `docs/VOLUME_BROWSER_QA.json`; ảnh ở `docs/qa/volume-*.png` (gitignored).

`pytest tests --collect-only` hiện còn ba lỗi import từ test đời cũ:
`test_day_loop.py` tham chiếu `OUTCOME_FEATURES/outcome_features` không còn trong
Engine V4; `test_learning.py` và `test_evaluation_gd8.py` tham chiếu hàm `weather`
không còn trong Learning V4. Không coi toàn bộ bộ test lịch sử là đã pass.
