## Bản cập nhật GD9.3

Chế độ Assisted / Manual / Shadow dùng chung cho ca, đặt ở đầu Tổng quan, Kế hoạch sản lượng và Giảm giá cuối ngày. Đã xóa ô chuyển hướng thừa ở An toàn & sự cố và cập nhật hướng dẫn. Xem [hướng dẫn GD9.3](docs/GD9_3_SHARED_MODES.md).

# GD9.2 — Sàn sản lượng khuyến nghị

Manager được duyệt dưới sàn90%baseline khi ghi lý do và audit; giữ mẻ4 và số dương. Xem [hướng dẫn GD9.2](docs/GD9_2_SOFT_PRODUCTION_FLOOR.md). Bao gồm bản sửa giá GD9.1.

# GD9.1 — Sửa Manager chỉnh giá

Ba chế độ ở ngay trang M1; dropdown giữ lựa chọn khi polling; Manual tạo bảng mới; mở lại chỉnh giá cùng mốc. Xem [hướng dẫn và phân tích báo cáo](docs/GD9_1_MANAGER_PRICING_FIX.md). Model/data/policy giữ nguyên.

# SmartFresh — Giai đoạn 9

Final QA & Deployment Readiness: health 200/503, structured API errors, Request ID tracing, offline backup/restore, GitHub CI và GO/NO-GO có bằng chứng cho demo local. Chưa nghiệm thu production/AEON; BigQuery chưa tích hợp; F04 vẫn bỏ khỏi UI.

Nâng cấp từ GD8 bằng patch, giữ environment/runtime và launcher cũ. Xem [hướng dẫn GD9](docs/GIAI_DOAN_9_HUONG_DAN.md) và [cách chép patch](docs/GD9_PATCH_GUIDE.md).

QA: `python scripts/run_qa.py`. GitHub Actions: `.github/workflows/ci.yml` (Ubuntu/Windows; chưa chạy trên repository của bạn).

# SmartFresh — Giai đoạn 8

Đối soát cuối ca, model registry, fresh holdout, promotion và rollback. F04 baseline vs M1+M2 đã gỡ khỏi giao diện theo yêu cầu.

Nâng cấp GD7: dùng patch, giữ environment/runtime và chạy launcher cũ. Xem [hướng dẫn GD8](docs/GIAI_DOAN_8_HUONG_DAN.md) và [cách chép patch](docs/GD8_PATCH_GUIDE.md).

# SmartFresh — Giai đoạn 7: Monitoring & Drift Dashboard
**Đang có GD6:** dùng ZIP PATCH, dừng server → chép đè vào thư mục có app.py → mở lại Start-Gemini.cmd cũ → Ctrl+F5. **Giữ nguyên .venv/runtime/.env/model/data**; không cần cài lại environment.

**Source mới:** Start-Gemini.cmd hoặc Start.cmd như trước; tài khoản local theo GD6.
Menu **Giám sát hệ thống** có 4 tab Dữ liệu/Mô hình/Vận hành/Cảnh báo. Nút **Tạo minh họa drift cô lập** giúp thử đầy đủ khi chưa có ca đã chốt.

- [Cách dùng PATCH](docs/GD7_PATCH_GUIDE.md)
- [Hướng dẫn GD7 đầy đủ](docs/GIAI_DOAN_7_HUONG_DAN.md)
- `python scripts/demo_gd7_check.py`: diễn tập API trên database tạm.

Full source bao gồm tất cả GD5/GD6 và bản sửa launcher; không đóng gói environment hay database phiên cũ.

---

# Bản bàn giao Giai đoạn 6 — Safety, Incident & Fallback
Full source **GD5 + sửa Start-Gemini + GD6**. Chạy **Start-Gemini.cmd** (không khởi động Ollama) hoặc Start.cmd.
Mở http://127.0.0.1:8000, lần đầu **tạo tài khoản Manager** bằng mật khẩu bạn tự chọn.
Menu **An toàn & sự cố**: Manual/Assisted/Shadow, phân quyền, incident và diễn tập phục hồi.

**Đọc:** [docs/GIAI_DOAN_6_HUONG_DAN.md](docs/GIAI_DOAN_6_HUONG_DAN.md).
**Thử tự động:** `python scripts/demo_gd6_check.py` (database tạm, không đổi ca của bạn).
Source gọn, không chứa .venv hoặc database phiên cũ. Hướng dẫn giữ runtime cũ nằm trong tài liệu trên.

---

# Bản bàn giao Giai đoạn 5 — Data Quality & Provenance
Mở **Start.cmd** để chạy demo. Vào **Dữ liệu đầu vào** để xem kiểm tra mới.
Hướng dẫn đầy đủ: [docs/GIAI_DOAN_5_HUONG_DAN.md](docs/GIAI_DOAN_5_HUONG_DAN.md).
File thử: **examples/gd5/** (ngày mục tiêu 16/08/2022).
Full source gọn, không kèm .venv/runtime của máy cũ. Giải nén vào thư mục mới.

---

# SmartFresh · Bakery Intelligence

Dashboard chạy local, dùng **hai mô hình LightGBM V9 đã huấn luyện sẵn** suy luận từ đầu vào mới, có upload dữ liệu, xác nhận quyết định, sổ giao dịch và Copilot tùy chọn (Gemini / OpenAI / Ollama).

Nguồn chính: **V9-20261020T063226Z-1-001.zip**, 173 tệp. Giao diện tham khảo Mockup draft 1.pdf, nền sáng và magenta theo hướng AEON Bakery PoC.

**Học từ dữ liệu:** mở `http://127.0.0.1:8000/?view=learning`. Nạp kết quả thực tế → huấn luyện ứng viên → kiểm tra trên ngày chưa học → xác nhận áp dụng. Có demo tách riêng và rollback; ca đang chạy giữ phiên bản cũ. Xem [định dạng dữ liệu và cơ chế đánh giá](docs/ADAPTIVE_LEARNING.md).

## Chạy trên máy hiện tại

Nếu dùng Gemini trên máy RAM thấp, chạy **Start-Gemini.cmd** (không bật Ollama), sau đó truy cập **http://127.0.0.1:8000**. `Start.cmd` là lối khởi động cũ có tích hợp Ollama.

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

## Kết nối Copilot qua Gemini / OpenAI / Ollama

Mở **Cài đặt AI**, nhập OpenAI API key và model có quyền truy cập. Key giữ trong bộ nhớ backend. Hoặc copy .env.example thành .env, điền key rồi khởi động lại.

Copilot dùng **OpenAI Responses API** và công cụ chỉ đọc để giải thích số liệu ca, không tự duyệt hoặc áp dụng. GPT có thể đề nghị ánh xạ cột chưa nhận diện; vẫn cần validation và preview.

Nút **Kết nối & gọi thử AI** gọi Responses API cùng công cụ dữ liệu ca, rồi hiển thị phản hồi thật, model và Response ID. Chỉ báo đã xác minh sau khi cuộc gọi thành công. Có thể mở thẳng http://127.0.0.1:8000/?view=settings khi server hoạt động.

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

## Bàn giao và kịch bản demo V1

Xem [Giai đoạn 4: QA Human Approval, ZIP và kịch bản demo](GIAI_DOAN_4_BAN_GIAO_VA_DEMO.md). Chạy `python -m pytest -q` và `python scripts/demo_gd4_check.py` để kiểm thử trên database tạm. Gói mã nguồn không chứa `.venv`, `.env` hoặc phiên SQLite.
