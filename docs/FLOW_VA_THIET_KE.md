# SmartFresh: flow sử dụng và hướng giao diện

> Phân tích ban đầu của bản replay. Trạng thái triển khai hiện tại và ZIP ngày 20/10 được cập nhật ở [IMPLEMENTATION_V9.md](IMPLEMENTATION_V9.md).

## 1. Kết luận thiết kế

Giữ cơ chế quản lý xem, chỉnh và duyệt. Tổ chức theo một ngày vận hành thay vì màn hình mang tên “AI Output”. Hai quyết định liên kết: M2 quyết định chuẩn bị bao nhiêu; M1 quyết định giá cuối ngày cho lượng còn lại. Cuối ngày ghi nhận kết quả để tạo lịch sử quan sát cho ngày tiếp theo.

Tài liệu này đối chiếu PDF mockup 15 trang, code run_v9.py, README V9, selection manifest và ba bảng đầu ra. Chưa audit toàn bộ mọi thư mục trong Drive. Mọi phần ghi “đề xuất” là thiết kế prototype, không phải chức năng đã có trong V9.

## 2. Flow theo ngày vận hành — đề xuất

1. **Vào ca:** chọn chi nhánh, ngày vận hành và chế độ Live demo / Simulation / Replay. MVP có thể chọn vai trò demo thay cho đăng nhập thực. Luôn hiển thị ngày, múi giờ Asia/Ho_Chi_Minh và nguồn dữ liệu.
2. **Kiểm tra dữ liệu:** tải CSV hoặc bộ kịch bản mẫu. Kiểm tra trùng SKU, ngày, số âm, thiếu lịch sử, tồn không khớp. Cho xem trước và sửa trước khi chạy. Lưu bản chụp đầu vào cùng thời điểm dữ liệu có sẵn.
3. **M2 — lập kế hoạch cho ngày mục tiêu:** lấy lịch sử bán trước ngày đó, lịch và dự báo thời tiết đã có tại thời điểm lập kế hoạch. Chạy model đã huấn luyện; cộng đệm theo SKU; làm tròn mẻ; áp dụng ngưỡng sàn. Hiển thị dự báo và sản lượng thành hai cột khác nhau.
4. **Quản lý duyệt kế hoạch:** giữ đề xuất, chỉnh số mẻ hoặc từ chối từng SKU. Chỉnh phải có lý do; lưu đề xuất gốc và số được duyệt. Nếu số mới vi phạm sàn/mẻ thì hiển thị lỗi hoặc yêu cầu xử lý ngoại lệ được thiết kế rõ.
5. **Xác nhận đã chuẩn bị:** ghi số thực tế hoàn thành. Đây là lượng tồn đầu ngày mô phỏng; không tự coi đề xuất là hàng đã được sản xuất.
6. **Bán trong ngày:** cập nhật bán, tồn, giá và doanh thu. Với demo, simulator phát sự kiện theo đồng hồ ảo; với dữ liệu nhập thủ công, người dùng ghi giao dịch hoặc tải CSV.
7. **M1 — từ 19:30:** tại các mốc 19:30, 20:00, 20:30, 21:00, 21:30, chụp tồn và doanh số vừa quan sát, tính đề xuất. Cho quản lý xem/duyệt từng SKU hoặc duyệt nhóm. Duyệt tạo bản ghi; thao tác áp dụng riêng cập nhật giá mô phỏng, không cập nhật POS thật.
8. **Theo dõi sau áp dụng:** các giao dịch tiếp theo dùng giá có hiệu lực. Tới mốc kế tiếp, tính lại từ tồn và tốc độ bán mới. Đề xuất chưa duyệt không tác động giá đang áp dụng.
9. **22:00 — chốt ngày:** khóa giao dịch của ngày, tính doanh thu, tồn/hủy, tỷ lệ bán hết. Lưu sổ giao dịch. Dữ liệu chốt được đưa vào lịch sử bán quan sát của ngày tiếp theo.
10. **Sang ngày kế:** tạo ngày mục tiêu mới và quay lại M2. Không tự lấy bánh hết hạn làm tồn có thể bán sang ngày mới.

### Lưu ý về thời điểm M2

Code V9 là vòng lặp theo ngày; chưa triển khai scheduler lúc 06:00 hoặc 22:00. Đề xuất MVP chốt M2 lúc 06:00 cho ngày vận hành hiện tại, sau khi đã có dữ liệu ngày trước. Đổi nhãn thành “Kế hoạch sản lượng” và ghi rõ “Ngày mục tiêu”. Nếu nhóm muốn lập tối hôm trước, thêm bản nháp và quy tắc chốt; không lấy doanh số chưa xảy ra làm đầu vào. Đừng đồng thời ghi 06:00, “hôm nay” và “ngày mai” cho cùng một kết quả như mockup hiện tại.

## 3. Cơ chế V9 cần thể hiện đúng trên UI

### M2

- LightGBM dự báo nhu cầu cơ sở. Feature gồm SKU, lịch, dự báo thời tiết, lag1, lag7, rolling7/14 và độ biến động lịch sử bán. Chỉ lấy lịch sử trước ngày mục tiêu.
- Đệm theo SKU được hiệu chỉnh từ residual, phối hợp residual riêng và chung. Quantile chính sách được chọn là **0,85**, không có nghĩa “model chắc chắn đúng 85%”.
- Sản lượng là max của: tối thiểu 4 bánh; dự báo cộng đệm làm tròn lên mẻ 4; ngưỡng **90% baseline** làm tròn lên mẻ 4. Ngưỡng này so với baseline do code tính, không tự thay bằng con số “định mức hiện tại” nhập tay.
- Baseline dùng bán quan sát 7 ngày trước, buffer 29%, điều chỉnh cuối tuần, làm tròn mẻ.
- V9 không có phép trừ tồn bánh từ hôm trước trong prepare_predict. Mockup đang mô tả “tồn đầu ngày” ảnh hưởng M2 thì cần bỏ hoặc ghi là tính năng mới cần xác minh hạn dùng và cập nhật code.
- V9 hiện dự báo từng ngày; biểu đồ dự báo 7 ngày tương lai là mở rộng chưa được chứng minh bằng output hiện tại.

**Bảng M2 nên có:** SKU/tên bánh, baseline, nhu cầu dự báo, đệm, ngưỡng sàn, số mẻ, sản lượng đề xuất, số được duyệt, chênh lệch so baseline, cảnh báo và lý do chỉnh. Bản replay khởi tạo chỉ hiển thị những cột có trong CSV, không bịa đệm hoặc baseline.

### M1

- Model dự báo phản ứng theo giá; optimizer chọn lịch giá dựa trên nhu cầu cơ sở, phản ứng giá, tồn, động lượng bán và doanh thu dự kiến. Không phải model phân loại trực tiếp “0%, 15%, 25%…”.
- Thang giảm trong code: **0, 20, 25, 30, 35, 40, 45, 50%**. Giá trị 8%, 15% trong mockup không thuộc thang hiện hành.
- Trần từng mốc: **20%, 25%, 35%, 45%, 50%** tương ứng 19:30 đến 21:30. Mức giảm đã áp dụng không được giảm ngược; chỉ thay đổi theo khung 30 phút.
- Từ 21:00 có sàn giảm 30% theo giả định nghiên cứu của V9. Đây chưa phải quy định AEON đã xác thực. 50% là mức có thể chọn khi thỏa ràng buộc, không tự áp dụng cho mọi SKU lúc 21:30.
- Nếu từ chối đề xuất làm giá hiện tại không còn thỏa sàn theo giờ, UI phải báo xung đột và yêu cầu quản lý chọn phương án hợp lệ; không âm thầm áp dụng hay bỏ qua quy tắc.

**Bảng M1 nên có:** SKU, tồn, bán 30/60 phút, giá gốc, giảm hiện tại, giảm đề xuất, giá sau giảm, trần/sàn giờ đó, cảnh báo tồn thấp, trạng thái duyệt, thời điểm áp dụng.

**Giải thích:** code đang trả reason như JOINT_FORECAST_REVENUE_PLANNING. Chưa có pipeline SHAP được đối chiếu. Không đưa các số SHAP trang mockup lên sản phẩm như kết quả tính thật. Nếu thêm SHAP cho model phản ứng giá, phải phân biệt giải thích dự đoán model với lý do optimizer chọn giá cuối cùng.

## 4. Trạng thái và xử lý dữ liệu đổi

Chuỗi trạng thái đề xuất: Nháp → Dữ liệu hợp lệ → Đang tính → Chờ duyệt → Đã duyệt → Đã áp dụng → Hoàn tất. Các nhánh bổ sung: Lỗi / Từ chối / Hết hiệu lực.

Mỗi lần chạy lưu run_id, chế độ, ngày mục tiêu, thời điểm mô phỏng, input_version, model_version, policy_version, kết quả và log. Khi tồn thay đổi trong lúc duyệt, đánh dấu đề xuất cũ hết hiệu lực và tính lại. Dùng khóa idempotency cho thao tác áp dụng để bấm hai lần không đổi giá hay ghi giao dịch hai lần. Ngày đã chốt không được tiếp tục nhận giao dịch; reset tạo scenario mới hoặc xóa riêng phiên demo theo lựa chọn rõ ràng.

## 5. Mô phỏng thời gian cho buổi trình bày

Không phụ thuộc giờ máy tính. Backend giữ simulation_time; mọi scheduler đọc cùng đồng hồ này. Thanh điều khiển có Chạy / Dừng, +30 phút, đến 19:30, đến 21:00, chốt 22:00, sang ngày kế, reset và seed.

Đề xuất một phút trình bày đại diện nhiều giờ vận hành; người dùng nên có thể dừng ở mốc duyệt. Nhảy thời gian phải xử lý từng sự kiện và từng mốc quyết định nằm giữa, không chỉ đổi chữ trên đồng hồ. Dừng ở bước cần quản lý duyệt. Không dùng giao dịch tương lai hoặc nhu cầu ẩn làm feature cho M1/M2. Nhu cầu ẩn chỉ dùng bên simulator/đánh giá để tính lost sales.

| Chế độ | Ý nghĩa | Khi nào dùng |
|---|---|---|
| Replay V9 | Phát lại CSV đã chạy, kết quả cố định | Demo ổn định và đối chiếu báo cáo |
| Simulation + inference | Đổi đầu vào, chạy model đóng băng, phát giao dịch có seed | Chứng minh input đổi thì quyết định và kết quả đổi |
| Live demo | Nhập/upload dữ liệu thật sự mới, chạy inference | Kiểm thử thao tác, chưa phải POS production |

Không gọi replay là đã chứng minh model phản hồi đầu vào mới. Khi mất mạng, replay và tính toán local vẫn dùng được; trợ lý OpenAI chuyển trạng thái không khả dụng. Không huấn luyện lại model mỗi lần nhập số liệu.

**Kịch bản demo đề xuất 5–7 phút:** mở M2 và giải thích dự báo khác sản lượng; duyệt kế hoạch; xác nhận chuẩn bị; chạy nhanh đến 19:30; tạo một tình huống tồn cao; xem M1 và duyệt; nhảy 21:00 để thấy sàn/trần; chốt 22:00; xem hủy/doanh thu/thiếu hàng rồi sang ngày sau. Các bước đổi input và duyệt thuộc backlog, chưa có trong replay hiện tại.

## 6. Vai trò ChatGPT/OpenAI — đề xuất

Flow nhập liệu: người dùng nhập “BK-001 còn 30 bánh, 30 phút vừa rồi bán 4” → assistant chuyển thành dữ liệu có cấu trúc → hiển thị bản xem trước để người dùng xác nhận → backend kiểm tra → backend gọi model/optimizer → UI cập nhật → assistant diễn giải từ JSON kết quả.

Các tool dự kiến: validate_inputs, run_m2, run_m1, compare_scenarios, explain_run. Các bước lưu/áp dụng quyết định vẫn có hành động duyệt rõ trên UI. Tool calling kết nối model ngôn ngữ với code của ứng dụng; ứng dụng thực thi hàm và đưa kết quả lại cho model.

ChatGPT hỗ trợ nhập liệu, giải thích và hỏi đáp. Nhu cầu, giảm giá, doanh thu và tồn lấy từ model/optimizer/sổ giao dịch. Assistant không tự tạo số SHAP, số hiệu quả hoặc tuyên bố model đã chạy nếu tool lỗi. Hỗ trợ nhập form trực tiếp ngay cả khi không dùng assistant.

Tích hợp bằng OpenAI API ở backend, API key qua biến môi trường, không đưa lên frontend hoặc GitHub. Ứng dụng local vẫn cần mạng khi gọi API. Bản khởi tạo chưa gọi API, chưa kiểm thử chi phí hay độ trễ. Tài liệu chính thức: https://developers.openai.com/api/docs/guides/function-calling và https://developers.openai.com/api/reference/overview .

## 7. Hướng giao diện hiện đại phù hợp quầy bakery

Đây là đề xuất thẩm mỹ, chưa phải bộ nhận diện AEON được phê duyệt. Nền #F6F5F2, bề mặt trắng, magenta #A80066 cho hành động chính, chữ #263048, xanh #287D5A cho hoàn tất, amber cho cảnh báo, đỏ cho lỗi. Dùng Segoe UI/Inter có hỗ trợ tiếng Việt; cỡ chữ thân 14–16 px, nút thao tác khoảng 44 px.

Sidebar gọn gồm Tổng quan, Kế hoạch sản lượng, Giảm giá cuối ngày, Theo dõi, Báo cáo, Kịch bản demo, Cài đặt. Không cần riêng một trang “Quy trình AI” nếu chỉ lặp lại flow; thay bằng trạng thái nhỏ trong từng màn hình. Header luôn có chi nhánh, ngày mục tiêu, giờ mô phỏng và badge dữ liệu.

Giảm đổ bóng đậm, logo quá lớn và nền ảnh sau bảng như mockup. Ảnh bánh phù hợp ở màn chào hoặc thumbnail SKU; màn vận hành ưu tiên đọc nhanh. Giữ một màu nhấn chính. Dùng tên tiếng Việt: Duyệt, Điều chỉnh, Từ chối. Cho mở chi tiết giải thích bên phải theo SKU; không luôn chiếm nửa màn hình.

Dashboard chỉ nên có 4–5 KPI có thể hành động: tồn hiện tại, SKU cần duyệt, doanh thu, nguy cơ hết hàng, thời gian tới mốc kế tiếp. Ghi rõ “dự kiến” cho ước tính và “đã ghi nhận” cho giao dịch. Doanh thu phải dùng đúng giá hiệu lực từng thời điểm, không lấy tất cả số đã bán nhân giá hiện tại.

## 8. Các lỗi mockup cần sửa cụ thể

- Trang M2 đang ghi “Đề xuất mức giảm giá”: đổi sang sản lượng chuẩn bị.
- Các dòng mẫu trang 14 cộng ra 650 → 633, không phải 550 → 530. Trong app luôn tính tổng từ dữ liệu.
- 32.000đ giảm 25% là 24.000đ; giá mẫu 22.500đ ở bảng M1 cần sửa.
- “Đang thực hiện” không nên tồn tại khi đã có output. Trạng thái phải được lấy từ run.
- “Đã duyệt” và “Đã thực thi” là hai trạng thái riêng; bổ sung bước áp dụng vào phiên mô phỏng.
- Mockup minh họa 6 SKU; V9 đang có 8. Lấy mã/tên và giá từ SKU master đã kiểm tra, không tự gán tên bánh cho mã chỉ có trong CSV.
- Báo cáo phải có trade-off thiếu hàng cùng với doanh thu và hủy. Lost sales từ nhu cầu ẩn chỉ gọi là số đo mô phỏng; khi áp dụng thực tế phải dùng chỉ báo/ước lượng phù hợp.
