# V6.06: cập nhật số bán và mục tiêu tồn 21:30

Chạy **Start.cmd**, mở **http://127.0.0.1:8000**, nhấn **Ctrl + F5**. Nếu đang xem ca 244 bánh cũ, bấm **Tạo ca mới với kế hoạch đã sửa** hoặc **Ca mới**, chọn 01/07/2022. Duyệt kế hoạch và xác nhận chuẩn bị. Ca cũ, giao dịch và doanh thu của nó được giữ nguyên; không thể bổ sung tồn ngược thời gian.

## Số bán và cập nhật giao diện

Bảng **Bán hàng trực tiếp theo từng sản phẩm** hiển thị số đã chuẩn bị, bán lũy kế từ mở cửa, tồn, doanh số 30/60 phút và doanh thu từng SKU. Trình duyệt lấy trạng thái mỗi giây; giám sát làm mới mỗi 3 giây. Có đồng hồ ca, revision và số dòng giao dịch để đối chiếu. Polling vẫn đọc dữ liệu khi tạm dừng đồng hồ, thay vì chỉ chạy khi clock enabled.

Ở ca cũ, tồn hết khoảng trưa nên 30/60 phút trước 19:30 không có giao dịch mới. Con số 0 đó không có nghĩa số bán cả ngày bằng 0. Ledger và bảng lũy kế là căn cứ để kiểm tra.

## Kế hoạch cung ứng

Trọng số XGBoost/RandomForest không đổi. Dự báo gốc M2 được giữ nguyên và hiển thị riêng. Lớp policy cung ứng dùng tải đông khách **4×** đã khai báo, kỳ vọng từ lịch sử quan sát trước test, buffer biến động Poisson z=2,33, dự trữ 8 chiếc/SKU và làm tròn mẻ 4. Không đọc lượt mua đã sinh của ngày test để tính kế hoạch.

Kịch bản khách có 25% lượt trước 17h, 75% từ 17h đến 22h. Đây là giả định công khai, không phải số đo AEON. Công suất của kịch bản cũng được khai báo tăng 4× giới hạn giả định gốc; không được coi đó là công suất lò/giao hàng đã xác minh. Mục tiêu còn hàng đến 21:30 **không phải bảo đảm**. Nếu giới hạn công suất không đủ hoặc thực tế hết hàng sớm, hệ thống báo không đạt, không sửa số bán để tạo kết quả đẹp.

Mỗi ca ghi tồn tại 21:30 và thời điểm hết hàng đầu tiên. Đã thử 4 seed 0, 1, 42, 606: đủ tồn cho từng SKU đến 21:30 trong các lượt kiểm tra. Mẫu thử không chứng minh SLA.

Kịch bản v2 ngày 01/07, seed 42 sinh 823 lượt mua. Joint chuẩn bị 1.244, bán 823, dư 421; baseline chuẩn bị 1.120, bán 823, dư 297. Hai nhánh cùng doanh thu 21.075.500đ, không mất lượt mua trong kịch bản này. Kết quả cho thấy buffer bảo thủ làm tăng dư hàng; không chứng minh M2/Joint tốt hơn baseline, không suy ra lợi nhuận khi chưa có chi phí. Không so trực tiếp với số 5,19% của kịch bản uniform trước bản sửa.

## Go/No-Go

Manifest và QA V9 trước đây không khớp mã/model V6.06 đã thay, nên release/QA fail là có căn cứ. Bản này có manifest mới và 30 kiểm tra V6.06 gắn với đúng release; chạy lại bằng `python scripts/verify_v606.py` trên môi trường có Edge và prototype cổng 8000.

Ca chưa đóng, Manager chưa ký đối soát hoặc chưa tới 21:30 được hiển thị **PENDING**, không tự coi là lỗi kỹ thuật. Model, dependency, checksum, công suất không đủ và hết hàng sớm vẫn báo FAIL khi không đạt. Không tự ký biên bản Manager, không tự đóng sự cố để ép GO.

## Copilot

Start.cmd khởi động Ollama local khi có sẵn. Model qwen3.5:4b đã được gọi thử thực tế và đọc được `get_session_context` cùng `get_model_evidence`. Bài kiểm tra kết nối dùng SKU thật của ca thay vì BK-001 cũ.

Copilot nhận dự báo gốc, policy cung ứng, đề xuất giá, giá hiện tại, bán lũy kế/30/60 phút, tồn, tốc độ bán, giao dịch đã phục vụ và thời tiết ngày trước nếu có. Không nhận nhu cầu ẩn, lost sales hoặc lượt mua tương lai. Lượt giao dịch đã phục vụ là proxy lưu lượng mua, không phải tổng khách qua cửa. M1 học bắt chước hành động, không phải model chứng minh uplift hay tối ưu giá nhân quả. LLM chỉ phân tích và giải thích; Manager vẫn duyệt.

Đây là kịch bản mô phỏng phát triển đã thay policy sau khi xem kết quả trước đó, không phải một test holdout mù mới hay kết quả chính thức trên private market gốc.
