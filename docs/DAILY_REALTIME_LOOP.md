# Chuỗi vận hành theo ngày và nguồn bán

Ứng dụng phân biệt **ca live nhập giao dịch** và **ca mô phỏng**. Không chèn lượt mua giả vào ca live. Khi ca live chưa nhận giao dịch và chưa xác nhận thực tế không bán, thiếu dữ liệu được đánh dấu rõ và M1 bị chặn duyệt giá. Nút **Tạo bản mô phỏng riêng** giữ ngày, forecast, lịch sử và phiên bản M1/M2 của ca nguồn, tạo sổ bán mới độc lập rồi chờ xác nhận sản lượng.

## Ý nghĩa số lượng

M2 là hồi quy nhu cầu kỳ vọng. 49,2 là giá trị thống kê hợp lệ, không phải sản xuất 0,2 chiếc bánh. Màn hình vận hành hiển thị ước lượng làm tròn, còn sản lượng chuẩn bị luôn là số nguyên và bội số 4. Tính toán nội bộ giữ kỳ vọng gốc để tránh sai số cộng dồn. Đệm hiển thị đã gồm quy đổi mẻ; giá trị thống kê và SHAP không phải số bánh đã bán.

M1/M2 không bốc số ngẫu nhiên: cùng artifact, lịch sử và forecast thì cùng dự báo/đề xuất. Mức giảm còn tuân thủ bậc giá, sàn/trần theo giờ và xác nhận quản lý. Đặc biệt, sàn chuẩn bị 90% baseline và mẻ 4 là policy V9, không phải tất cả đều do LLM tự học.

## M3 — nguồn lượt mua mô phỏng

Mô hình độc lập lưu ở `models/arrivals/model.json`, huấn luyện bằng `scripts/train_arrivals.py`:

- Fit Poisson mean với SKU, thứ, lượng mưa và nhiệt độ forecast trên 384 dòng V9 từ 01/06 đến 18/07/2022.
- Chọn mức regularization và hiệu chỉnh residual trên 19/07–01/08. Không dùng M2 để quyết định số khách của ngày đang chạy.
- Hình sin/cos mùa vụ theo năm đã bị loại: nguồn vài tháng không đủ cơ sở học mùa cả năm. Phép thử ban đầu dùng 02–15/08 chỉ là giai đoạn phát triển. Kiểm tra cuối riêng trên 128 SKU-ngày 16–31/08: MAE khoảng 3,04 chiếc/ngày, baseline trung bình SKU khoảng 3,15. Đây chỉ là điểm trên nguồn tổng hợp này.
- Tạo số yêu cầu mua nguyên bằng kỳ vọng đã fit cộng residual lấy mẫu từ tập hiệu chỉnh, có biên giới hạn theo train; không dùng Poisson noise quá rộng khi nguồn ít biến động. Seed + ngày + weather + hash artifact tạo lượt mua tái lập.
- Tỉ lệ yêu cầu mua trong 18:30–19:00 và 19:00–19:30 được ước lượng từ `sales_last30`/`sales_last60` của nhãn train V9. Phần đầu ngày trước 18:30 vẫn dùng hình dạng Beta giả định. Phân bố muộn và promo response kế thừa hiệu chỉnh V9, không phải quan sát intraday thật mới tìm thấy.
- Mỗi yêu cầu cơ sở tương ứng một chiếc. Lượt promo chỉ được thực hiện nếu mức giảm **đang áp dụng** đạt ngưỡng; giá chờ duyệt không được dùng để tăng bán. Có nhu cầu nhưng hết hàng thì tăng bộ đếm không đáp ứng trong mô phỏng, không ghi giao dịch bán quá tồn.
- Bộ tạo không đọc dự báo M2 hoặc future ledger vào ngày hiện tại. M1 có thể dùng cùng nguồn calibration V9 nên không được dùng lợi nhuận trên simulator này để tuyên bố chính sách M1 đã được kiểm chứng độc lập ở cửa hàng.

ZIP thiếu quan sát lượt đến intraday gốc. Nguồn này là synthetic V9, **không phải dữ liệu bán AEON quan sát thực tế**. Cần POS theo thời gian, ghi nhận hết hàng, thử nghiệm giá và forecast đúng thời điểm để hiệu chỉnh/kiểm chứng tính thực tế. Không có cơ sở hứa simulator giống cửa hàng chỉ vì đã fit một model.

## Đồng hồ backend

Ca mô phỏng mới có lựa chọn **Tự bán sau xác nhận chuẩn bị**. Sau xác nhận, đồng hồ bắt đầu tại 08:00. Có các tốc độ 1×, một giây bằng 1/5/30 phút ảo. Thread backend xử lý khoảng thời gian, trừ tồn và ghi ledger; đóng tab vẫn chạy nếu backend còn chạy.

Mặc định **Dừng ở bước duyệt**: dừng tại 19:30, 20:00, 20:30, 21:00, 21:30 để có thể đọc và xác nhận. Sau áp dụng hoặc từ chối hợp lệ, bán tiếp. Bỏ lựa chọn này thì thời gian và bán tiếp tục khi giá đang chờ; đề xuất được tính lại từ tồn và doanh số mới, xác nhận cũ hết hiệu lực. Khi chậm trong một slot, optimizer giảm lượng cầu còn lại của slot theo thời gian thực còn lại. Tới 22:00, đề xuất chưa áp dụng hết hiệu lực; ca chờ chốt, không tự áp dụng giá.

Khởi động lại backend tạm dừng đồng hồ, không tự chạy bù qua nhiều giờ đã tắt máy. Seed, phiên bản và hash simulator được ghim theo ca; ca v1 cũ vẫn dùng generator v1. Không đổi generator giữa một ca đang chạy.

## Bán 30 phút / 60 phút

Đây là **số chiếc đã thực bán trong cửa sổ gần nhất của chính ca đó**, tính từ ledger tại thời điểm ra quyết định; không phải nhu cầu dự báo, lượt đến chưa mua hoặc tổng bán cả ngày. Hết hàng có thể khiến cửa sổ bán bằng 0 dù vẫn có yêu cầu mua. Nếu live không có nguồn giao dịch thì hiển thị thiếu dữ liệu và chặn đề xuất, thay vì coi 0/0 là kết quả thực tế.

## Ngày nào dùng dữ liệu ngày đó

19/08/2022 là thứ Sáu; 19/09/2022 là thứ Hai. Hai ca có forecast, lịch sử bán D−1/D−7, rolling 7/14 ngày và các lượt mua mô phỏng riêng. Không dùng sổ tháng 9 để dự báo tháng 8. Với kịch bản lịch sử V9, các ngày trước chưa được người dùng vận hành được warm-up bằng mô phỏng có seed; giao diện ghi rõ đó là lịch sử nền mô phỏng, không coi là POS thật.

Ca đã chốt ở quá khứ sẽ bổ sung/ghi đè kết quả bán của đúng ngày, đúng chế độ và seed. Truy vấn không còn giới hạn 30 ca gần nhất. Biểu đồ lịch sử lấy `input_history` của ca đang xem; không còn gắn cố định 7 ngày trước 16/08.

Sau chốt ngày, **Tạo kế hoạch ngày kế tiếp** lấy bán thực ghi nhận vào lag ngày trước; tồn/hủy và hết hàng được lưu trong snapshot đầu vào. Nhiệt độ/mưa/ngày lễ phải là forecast của ngày mới, không sao chép weather hôm trước. Ngoài lịch V9 phải tải forecast mới, không tự bịa thời tiết.

## Tồn hủy được học ở đâu?

Model M2 gốc chỉ có lag bán/lịch/thời tiết, không được gắn nhãn là đã dùng feature tồn hủy. Recipe học M2 mới bổ sung 7 đặc trưng từ **ngày quá khứ**: chuẩn bị, tồn hủy, hết hàng và bán giảm giá D−1; tồn hủy D−7; tỉ lệ hủy 7 ngày; tồn hủy trung bình cùng thứ 4 tuần. Số bán hôm nay được liên kết ngay vào lịch sử cho hôm sau; trọng số mới chỉ được dùng khi có đủ nhãn hợp lệ, ứng viên đạt kiểm tra và được xác nhận.

Xem [ADAPTIVE_LEARNING.md](ADAPTIVE_LEARNING.md) về loại các nhãn bị hết hàng/khuyến mãi, split thời gian và điều kiện đưa model mới vào dùng. Không tự train lại trọng số sau một ngày rồi khẳng định tốt hơn.

## Kiểm chứng

Unit test kiểm tra seed và độc lập với M2, dòng mua cuối giờ, chặn live thiếu feed, clock không cần trình duyệt, pause/resume và stale proposal, bảo toàn tồn/doanh thu, chốt → ngày mới, ngày/thứ/weather khác nhau và không đọc dữ liệu tương lai. Browser QA chạy trên DB riêng: live thiếu feed → fork mô phỏng → xác nhận chuẩn bị → đóng tab mà clock vẫn chạy → 19:30 → xử lý giá → chốt → kế hoạch hôm sau, kiểm tra số nguyên và mobile.
