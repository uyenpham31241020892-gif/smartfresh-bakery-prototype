# M1 v8: giảm muộn có ngân sách, giải thích trước duyệt, lịch sử baseline

## Giá

Giữ nguyên hai model XGBoost đã train trong v7, cùng trọng số và cùng dòng khách.
Không retrain bằng test hoặc doanh số POS tháng 7–8. Thay lớp chọn hành động giá:

- Ưu tiên từ 21:00. Trước đó chỉ xét từ 19:30 nếu phần dư dự kiến ít nhất
  max(12 chiếc, 25% chuẩn bị), chiếm ít nhất 60% tồn và quan sát được sức bán chậm.
- Trước 21:30 trần tự đề xuất là tổng 10% so niêm yết. Từ 21:30 chỉ xét tổng 20%
  khi dư đáng kể. Không tự đề xuất 30/40%; không cộng dồn phần trăm.
- Tính số đã nhượng giá trong ngày + phần nhượng dự kiến trên lượng còn bán được.
  Ngân sách dự kiến là 1% doanh thu niêm yết tham chiếu khi giảm sớm, 2% từ 21:00,
  2,5% từ 21:30. Đây là ngân sách tại thời điểm ra quyết định, không phải cam kết
  giới hạn thiệt hại thực tế nếu sức bán khác dự kiến.
- Còn kiểm tra đệm phục vụ đến 21:30, số bán thêm hòa vốn, doanh thu giả định và
  sàn giá vốn giả định 45% niêm yết. Giá vốn chuẩn bị đã phát sinh không trừ hai lần.
- Giá đang áp từ policy cũ không tăng ngược, hóa đơn và tồn không sửa. Đề xuất cũ
  chưa áp có thể được thay bằng đề xuất mới qua thao tác nội bộ có audit.

`price_history.py` đọc đúng các ca trước đã chốt trong nhánh của ca đang chọn,
ngày nhỏ hơn ngày hiện tại và cùng thị trường. Dùng tốc độ cùng giờ, lượng bán còn
lại của các ngày trước, điều chỉnh theo sức bán hôm nay. Hiển thị hôm trước, hai ngày
trước, tuần trước, tháng trước. Nếu thiếu ca cùng kịch bản, baseline proxy chỉ được
ghi là tham chiếu khác thị trường; không lấy tốc độ proxy trộn thẳng vào dự báo 4x.

Phản ứng giá vẫn là giả định E=2, không phải độ co giãn đã học từ thử nghiệm AEON.
Kiểm tra phát triển trên lịch validation 60 ngày được lưu trong
`v606/V606_M1_remaining_v7/late_first_sensitivity_report.json`. Validation đã dùng
phát triển policy, không phải kiểm tra độc lập. Luôn công bố cả hệ số phản ứng 0/1/2;
không chọn tham số nhằm làm đẹp một ngày test.

## Giải thích

Lỗi trước đây: model Ollama có lúc không phát tool call dù được yêu cầu, rồi luồng
Copilot từ chối câu trả lời không có căn cứ. Luồng đề xuất hiện thực thi công cụ
`get_model_evidence` ở máy chủ cho từng SKU, chụp bất biến đúng đề xuất trước duyệt.
Không chờ model tự chọn gọi công cụ, không chấp nhận số liệu bịa để né lỗi.

API state trả ngay lời giải thích có số liệu từ bằng chứng. Copilot nhận sẵn bằng
chứng và chọn ba SKU cần chú ý cùng hành động phù hợp qua JSON schema. Máy chủ
chèn số liệu đã kiểm tra; AI không được tự tạo số, duyệt hay sửa giao dịch. Khi model
tạm lỗi, hiển thị rõ lời giải thích trực tiếp từ bằng chứng và cho thử tổng hợp lại.
Không giả câu mẫu là phản hồi đã sinh thành công từ LLM.

M1/M2 có hàng đợi riêng với báo cáo để không phải chờ phân tích báo cáo dài.
Job và lời giải thích tức thời cùng dùng snapshot bất biến; duyệt không kích hoạt
mới việc giải thích. Đã gọi thật qwen3.5:4b và nhận bản tổng hợp khi ca còn price_pending.

## Baseline

`scripts/build_baseline_history.py` kiểm checksum ZIP 02 rồi chỉ xuất hai nguồn quan
sát `baseline_daily_OBSERVED.csv`, `observed_15min.csv` và SKU master. Đối soát tổng
lượng/revenue theo khoảng với tổng ngày, kiểm prepared = sold + stock.

1197 SKU-ngày / 171 ngày quan sát trong 02/01–30/06/2022, doanh thu nguồn tổng
782.772.100 ₫. Report tab **Lịch sử baseline** có phạm vi 30/90/180 ngày, doanh thu,
chuẩn bị/bán/tồn theo ngày, bảng chi tiết và Copilot đọc đúng nguồn baseline.
Không trộn vào session/ledger, không cộng baseline vào doanh thu ca mới, không biến
baseline train thành bằng chứng hiệu quả độc lập so với AI. Đây là proxy áp giá
khảo sát tham chiếu, không phải doanh thu lịch sử AEON đã xác minh. Ngày thiếu để trống.
