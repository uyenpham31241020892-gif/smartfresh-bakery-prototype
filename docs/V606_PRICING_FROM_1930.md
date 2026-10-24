# Đề xuất giá theo tình trạng bán từ 19:30 — policy v5

## Nguyên nhân lặp lại

Số bán không bị đặt giống nhau từng ngày. Ví dụ sổ ca seed 42 lưu `TP-DN-001` bán 103 chiếc ngày 01/07 và 136 chiếc ngày 02/07. Generator lấy mẫu theo ngày/seed/SKU; cùng ngày và seed chạy lại cho cùng luồng khách để đối chiếu. Phân phối trung bình và 75% buổi tối vẫn là giả định cố định, chưa phải dữ liệu lưu lượng AEON thực.

Mức giảm và giờ đề xuất lặp nhiều vì classifier M1 học bắt chước baseline có các mức giá tham chiếu ít lựa chọn, và adapter cũ còn chặn cứng trước 21:00. Chỉ xóa điều kiện giờ vẫn chưa đủ: classifier được học để HOLD trước 21:00.

## Thay đổi

Engine mới `V606-frozen-prototype-contextual-price-v5` dùng policy `OBSERVED_SURPLUS_FROM_1930_V1`:

1. Tại 19:30, 20:00, 20:30, 21:00 và 21:30, đọc tồn và số bán 30/60 phút của chính SKU trong ca hiện tại.
2. Gọi cả classifier M1 và model dự báo bán 30 phút đã train dưới hành động ghi nhận. Feature vẫn theo allowlist và chuẩn hóa mô phỏng 4× về thang train; không đọc tương lai/nhu cầu ẩn.
3. Pace dùng mức lớn hơn giữa số bán 30/60 phút và dự báo M1. Ngoại suy đến 22:00 để tính phần dư sau reserve 4 chiếc. Chỉ xét giảm nếu dư vượt max(4 chiếc, 8% lượng chuẩn bị).
4. Trước 21:30, giữ giá nếu tồn chưa vượt lượng dự kiến bán đến 21:30 cộng đệm. Đây là bảo vệ theo ước tính, không bảo đảm phục vụ.
5. Nếu dư đáng kể, mức đề xuất 5/10/15/20% tùy tỷ lệ dư và thời gian còn lại; với SKU có giá giảm tham chiếu thì không đề xuất thấp hơn giá tham chiếu đó. Hai SKU chưa có mức giảm khảo sát vẫn có thể tham gia, giới hạn đề xuất 20% là giả định của policy.
6. Giá không tự tăng lại, không giảm chồng phần trăm trên giá đã giảm. HOLD không yêu cầu duyệt. Thay đổi phải qua **Duyệt → Áp dụng**; từ chối giữ giá, hóa đơn cũ không sửa.

UI giải thích riêng lượng tồn, số bán, lượng dự kiến bán tiếp và tồn dư cho từng món; có mục xem lý do những món giữ giá. Mức giảm có thể trùng khi tình trạng rơi vào cùng ngưỡng; không thêm ngẫu nhiên vào giá chỉ để trông khác nhau.

## Bằng chứng và giới hạn

Ca phát triển 01/07 seed 42 đã đề xuất ngay 19:30: một số món giảm 5%, một số giảm 10%, hai món giữ giá. Browser test kiểm tra giá vẫn bằng 0% trước duyệt và sau duyệt, chỉ đổi sau bước áp dụng. Unit tests kiểm tra cùng giờ nhưng khác pace/tồn cho hành động khác, bảo vệ tồn đến 21:30, không tăng giá, giá tham chiếu, ngày khác có luồng bán khác và giữ nguyên quy tắc của engine v4 khi mở lịch sử.

**Đây là M1 dự báo kết hợp quy tắc tồn dư đã khai báo, không phải bằng chứng model học được uplift của giảm giá sớm.** Không đổi/training lại trọng số M1 trong lần sửa này. Luồng khách không sinh thêm người mua chỉ vì giảm giá. Vì vậy có thể làm giảm doanh thu mà chưa giảm tồn trong kịch bản không có phản ứng giá; không gọi policy này là tối ưu lợi nhuận hoặc hứa tăng bán. Quản lý xem căn cứ và có thể giữ giá.

Engine v3/v4 của các ca cũ được ghim nguyên; code adapter gốc vẫn giữ để tái lập lịch sử. Policy mới áp dụng cho ca/ngày mới sau khi cập nhật. Không đổi nguồn khách, sửa giao dịch cũ, hoặc dùng kết quả tháng 7–8 để train. Đây tiếp tục là phát triển prototype, không phải holdout độc lập mới.

Để tiếp tục: Ctrl+F5 → chốt ca khi đến 22:00 → **Tạo kế hoạch ngày kế tiếp**. Phần giảm giá tối sẽ xét từ 19:30.
