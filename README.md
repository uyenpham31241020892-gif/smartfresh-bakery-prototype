# SmartFresh · Bakery Intelligence

Dashboard chạy local, dùng **hai mô hình LightGBM V9 đã huấn luyện sẵn** suy luận từ đầu vào mới, có upload dữ liệu, xác nhận quyết định, sổ giao dịch và OpenAI Copilot.

Nguồn chính: **V9-20261020T063226Z-1-001.zip**, 173 tệp. Giao diện tham khảo Mockup draft 1.pdf, nền sáng và magenta theo hướng AEON Bakery PoC.

**Học từ dữ liệu:** mở `http://127.0.0.1:8000/?view=learning`. Nạp kết quả thực tế → huấn luyện ứng viên → kiểm tra trên ngày chưa học → xác nhận áp dụng. Có demo tách riêng và rollback; ca đang chạy giữ phiên bản cũ. Xem [định dạng dữ liệu và cơ chế đánh giá](docs/ADAPTIVE_LEARNING.md).

## Chạy trên máy hiện tại

Mở **Start.cmd**, sau đó truy cập **http://127.0.0.1:8000**.

Python 3.12 riêng được chuẩn bị trong .tools/python312, không thay Python hệ thống. PowerShell:

    .\.tools\python312\python.exe app.py

## Chạy trên máy mới

Cài Python 3.12, rồi:

    py -3.12 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv\Scripts\python.exe app.py

Model native, metadata, dữ liệu tuyển chọn và reference có sẵn trong repository; không cần ZIP gốc để chạy. Python 3.14 gặp lỗi native dependencies trên máy hiện tại.

## Trải nghiệm

1. Mở **Kế hoạch sản lượng**. M2 đã suy luận mới cho ngày mẫu 16/08/2022.
2. Xem từng SKU: nhu cầu, buffer, baseline, sàn, sản lượng và TreeSHAP thật.
3. **Duyệt kế hoạch**, rồi **Xác nhận đã chuẩn bị**.
4. Tới **19:30**. M1 tự tính đề xuất từ tồn và doanh số vừa quan sát.
5. **Duyệt giá**, rồi **Áp dụng giá đã duyệt**. Giao dịch tiếp theo dùng giá mới.
6. Tới 22:00; hệ thống dừng từng mốc cần xác nhận. Qua 21:30, tới 22:00 và **Chốt ngày**.
7. Xem báo cáo, xuất sổ CSV và mở nhật ký quyết định.

Ca được lưu ở runtime/smartfresh.sqlite3. **Ca mới** tạo phiên riêng; **Lịch sử ca** mở lại kết quả. Thao tác có revision và audit.

## Upload dữ liệu

Trong **Dữ liệu đầu vào**, chọn ngày rồi tải CSV, XLSX hoặc ZIP tối đa 20 MB. Xem preview và xác nhận; backend tự chạy M2 hoặc nhập giao dịch, tính lại M1 nếu cần.

| Dữ liệu | Cột cần thiết |
|---|---|
| Lịch sử | date, sku_code, sold_qty — chỉ ngày trước ngày mục tiêu |
| Weather | date, forecast_rain_mm_previous_day1, forecast_temperature_max_c_previous_day1, issued_at |
| Giao dịch | sku_code, minute, quantity — phút bằng đồng hồ ca hiện tại |

Ngày mới ngoài V9: Excel hai sheet history/weather, hoặc ZIP có history.csv và weather.csv. issued_at phải có múi giờ, không sau 06:00 ngày mục tiêu. File mẫu tải trên dashboard. ZIP V9 gốc cũng được nhận diện lịch sử/forecast.

Model hỗ trợ đúng 8 SKU của SKU master. SKU mới cần bổ sung dữ liệu và đào tạo/kiểm chứng model.

## GPT thật

Mở **Cài đặt AI**, nhập OpenAI API key và model có quyền truy cập. Key giữ trong bộ nhớ backend. Hoặc copy .env.example thành .env, điền key rồi khởi động lại.

Copilot dùng **OpenAI Responses API** và công cụ chỉ đọc để giải thích số liệu ca, không tự duyệt hoặc áp dụng. GPT có thể đề nghị ánh xạ cột chưa nhận diện; vẫn cần validation và preview.

Nút **Kết nối & gọi thử GPT** gọi Responses API cùng công cụ dữ liệu ca, rồi hiển thị phản hồi thật, model và Response ID. Chỉ báo đã xác minh sau khi cuộc gọi thành công. Có thể mở thẳng http://127.0.0.1:8000/?view=settings khi server hoạt động.

**Chưa kiểm thử gọi OpenAI thật vì chưa có API key.** Khi chưa cấu hình, ứng dụng báo chưa kết nối; không trả lời GPT giả.

## Kiểm tra

    .\.tools\python312\python.exe -m pytest -q
    node --check web\app.js

Máy mới cài requirements-dev.txt để chạy pytest. Browser QA cần server hoạt động và Microsoft Edge:

    .\.tools\python312\python.exe scripts\browser_qa.py

Đã đạt 66 test backend, đối chiếu hàm policy V9 gốc và đối soát 480 SKU-ngày; browser QA desktop/mobile và luồng học dữ liệu không ghi nhận lỗi JavaScript. Provider API dùng stub trong unit test; Ollama đã được gọi thật trên máy này. Gemini/OpenAI cần key/quota để kiểm chứng tài khoản thật. Lỗi 429 được phân loại riêng thành quota/số dư, hạn mức chi tiêu và giới hạn tốc độ; không tự gọi lại khi thiếu credit/quota. Ảnh và kết quả ở docs/qa/.

## Giới hạn cần biết

- Chạy **inference thật** từ model đã huấn luyện; màn hình **Học từ dữ liệu** huấn luyện ứng viên LightGBM mới khi đủ kết quả thực tế. Cần đạt đánh giá và được xác nhận trước khi áp dụng. Không tự train từ mọi file, chưa fine-tune LLM.
- Nhu cầu và phản ứng giá V9 là mô phỏng; chưa xác nhận chất lượng trên POS AEON thực.
- ZIP thiếu observations gốc tháng 9. Demo dùng bộ sinh lượt mua mới có seed; output tháng 9 giữ ở **Đối chiếu V9**.
- WAPE run audit là **11,953181%**. WAPE **12,077197%** thuộc workbook/hash khác.
- Chưa đủ nguồn chứng nhận tái huấn luyện end-to-end cả hai model. Hash artifact và kết quả inference đã được kiểm tra.

Xem [triển khai](docs/IMPLEMENTATION_V9.md), [nguồn](docs/SOURCES.md) và [inventory](docs/source_inventory.json) để đọc cơ chế, giả định và giới hạn.
# Ollama và Gemini

Trong **Cài đặt AI**, chọn Ollama, Gemini hoặc OpenAI. Mỗi lần kết nối đều gọi model thật qua vòng đọc công cụ; chỉ sau khi thành công mới thay kết nối hiện tại. Không tự chuyển sang cloud khi local lỗi.

- Ollama: chạy `Setup-Ollama.cmd` một lần để tải CLI chính thức và `qwen3.5:4b` vào thư mục dự án. Cần vài GB tải xuống và dung lượng lưu trữ. `Start.cmd` tự khởi động CLI đã cài trên loopback. Chọn Ollama, giữ tên model, bấm kết nối; không cần API key. Không có phí API, vẫn dùng điện và phần cứng của máy.
- Gemini: tạo key tại https://aistudio.google.com/api-keys, chọn Gemini, nhập key trực tiếp vào dashboard và bấm kết nối. Mặc định `gemini-3.8-flash`; có thể đổi tên model theo quyền project. Google AI Pro trong ứng dụng Gemini không bảo đảm quota API; kiểm tra project/free tier/billing tại AI Studio. Không gửi key trong chat. Free tier có giới hạn và điều khoản dữ liệu khác paid tier.
- Để giữ cấu hình sau restart: dùng `.env.example` làm mẫu, đặt `AI_PROVIDER=Ollama` hoặc `AI_PROVIDER=Gemini` và các biến model/key tương ứng. Key nhập qua UI chỉ giữ trong bộ nhớ phiên chạy.

M1/M2 đã huấn luyện tính nhu cầu, sản lượng và lịch giá. LLM đọc kết quả để giải thích và ánh xạ cột, không được fine-tune riêng trên V9, không có công cụ duyệt/áp dụng giá. Model local nhỏ có thể suy luận hoặc giải thích kém; cloud cũng có thể sai. Câu trả lời không đọc công cụ bị từ chối, nhưng việc đọc công cụ không bảo đảm mọi câu giải thích đều đúng. Cần đánh giá trên tình huống thực tế trước vận hành.

Kiểm thử provider sử dụng HTTP giả lập để kiểm tra truyền bằng chứng, giữ thought signature Gemini, không làm thay đổi ca và từ chối model không đọc tool. Đây không phải kết quả đánh giá chất lượng model thực hay bằng chứng đã gọi Gemini bằng tài khoản người dùng.


Xem [c? ch? realtime, m? ph?ng v? chuy?n ng?y](docs/DAILY_REALTIME_LOOP.md).
