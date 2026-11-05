# SmartFresh — giao diện vận hành và tài khoản cố định

Bản cập nhật 31/10/2026: bỏ trang Tổng quan, mở mặc định Kế hoạch sản lượng; làm gọn chú thích và giao diện. Hai Manager cố định là manager.chau và manager.uyen. Đăng ký tại màn hình đăng nhập chỉ tạo Staff. Các Manager cũ khác được chuyển thành Staff khi khởi động.

Nhân viên được tạo ca Assisted, chạy đồng hồ, xác nhận đã chuẩn bị sau phê duyệt, áp giá đã được Manager duyệt, ghi nhận bán và chốt ca. Không sửa/duyệt sản lượng hoặc giá, thay chế độ, quản lý sự cố/model/tài khoản/cấu hình. Máy chủ kiểm tra quyền độc lập giao diện. Hai Manager có toàn bộ quyền ứng dụng; khóa model V4 và quy tắc nghiệp vụ vẫn giữ nguyên.

Chạy Start-Gemini.cmd hoặc Start.cmd, Python 3.12. Mật khẩu bàn giao gửi riêng, không nằm trong source; manager_accounts.json chỉ lưu salt và hash scrypt. Không tự sửa file này. Chia sẻ cùng một server/database để Châu và Uyên cùng truy vết lịch sử; các bản giải nén chạy độc lập không tự đồng bộ dữ liệu.

Không chép runtime cũ sang khi chưa sao lưu. Nếu cần giữ ca cũ: sao lưu thư mục runtime trước rồi thay source khi server đã dừng.

Bằng chứng QA cũ trong docs là của bản trước. Xem docs/UI_AUTH_CHECK.json cho kiểm tra của cập nhật này. Chưa xác nhận chạy Windows hoặc API Gemini/POS thật.

# SmartFresh — Prototype gốc tích hợp V4

Bản này phát triển tiếp từ `smartfresh-bakery-prototype-Kuyn (1)(1).zip`. Giữ dashboard và các nhóm chức năng của prototype; thay toàn bộ model/dữ liệu vận hành cũ bằng V4 và sửa lớp kết nối cho đúng hợp đồng V4. Không sử dụng bản app V4 rút gọn đã gửi trước đó.

## 1. Mở app trên Windows

1. Giải nén ZIP ra thư mục ngắn, ví dụ `C:\SmartFresh_V4_Prototype`. Mở thư mục có `app.py`, `Start-Gemini.cmd`, `Start.cmd`.
2. Máy cần Python **3.12**. Nhấn `Start-Gemini.cmd` nếu muốn chọn Gemini cho Copilot; hoặc `Start.cmd` để dùng cấu hình AI trong `.env`/môi trường.
3. Lần đầu, launcher tạo `.venv` và cài thư viện V4. Các lần sau dùng lại môi trường; chỉ cài khi thiếu/sai phiên bản hoặc requirements thay đổi. V4 cần **scikit-learn 1.9.1**; môi trường cũ 1.6.1/1.8 không chạy đúng bundle này.
4. Khi health check đạt, cửa sổ in `http://127.0.0.1:8000` và mở trình duyệt. Giữ cửa sổ đó mở trong lúc demo. Nếu port bị chiếm, đóng cửa sổ SmartFresh cũ; launcher không tự tắt chương trình khác.
5. Lần đầu app yêu cầu **tự tạo tài khoản Manager**, mật khẩu tối thiểu 8 ký tự. Không có mật khẩu mặc định. Các lần sau đăng nhập tài khoản đã tạo trên máy.
6. Nếu có lỗi: đọc dòng lỗi ở cửa sổ chạy và `runtime/server.log`. Đừng mở app trực tiếp trong ZIP; đừng ghép hai bộ `data`/model vào nhau.

Không phải chạy lại train/test. Lệnh `py -3.12 launch.py` chỉ dựng môi trường và mở dashboard.

## 2. Những chức năng được giữ

| Chức năng | Hoạt động với V4 |
|---|---|
| Tổng quan | Kế hoạch, tồn, số bán, doanh thu, lịch sử nguồn của ca |
| Kế hoạch sản lượng | M2 V4, duyệt/từ chối, Manager sửa có lý do, đúng mẻ/công suất mẫu |
| Giảm giá cuối ngày | M1 V4, Assisted/Manual/Shadow, duyệt rồi áp giá, giá theo từng SKU |
| Giao dịch & theo dõi | Sổ giao dịch, bán 30/60 phút, tồn và xuất CSV |
| Báo cáo hiệu quả | Biểu đồ ngày/giờ/SKU, lịch sử ca, tham chiếu baseline từ cùng bộ nguồn V4, đối soát và xác nhận |
| Dữ liệu đầu vào | CSV/XLSX/ZIP, xem trước, cách ly lỗi, xác nhận nhập, lịch sử nhập/hash |
| Giám sát | DQ, MAE/WAPE trên quan sát đủ điều kiện, tỷ lệ censor, drift PSI/KS, M1 safety, API/jobs, cảnh báo/tiếp nhận |
| An toàn & sự cố | Manager/Staff/Viewer, diễn tập lỗi, Rolling-7 thủ công, tiếp nhận → Verify → đóng sự cố |
| Model Registry/lifecycle | Model V4 ghim theo ca, hash, lịch sử, snapshot và khôi phục triển khai V4 |
| Học từ dữ liệu | Thu/lưu kết quả ca đủ điều kiện, tách real/demo; trọng số V4 tiếp tục được khóa |
| GO/NO-GO | Health, checksum release, đối soát, quyền/xử lý sự cố và bằng chứng QA local |
| Nhật ký | Người thao tác, lý do, phiên bản ca/model, giá trước/sau và request ID |
| Copilot | Gemini/OpenAI/Ollama, hỏi đáp và giải thích từ công cụ đọc dữ liệu V4 |

Train/tune/promotion một model khác không được bật: quyết định nhóm dùng duy nhất V4; prototype đầu vào cũng đã khóa các endpoint huấn luyện. Lifecycle khôi phục **bản sao triển khai của cùng V4**, không nạp lại model cũ, không tạo V4.1. Đây là phân biệt giữa phiên bản model và bản sao để phục hồi.

## 3. Demo một ca hoàn chỉnh

1. Chọn **Ca mới**, ngày **02/05/2022**, chế độ **Mô phỏng V4**, nguồn **Thị trường V4 có phản ứng giá giả định gốc** (mặc định). Để tự điều khiển, bỏ chọn tự bán sau xác nhận; hoặc tạm dừng đồng hồ sau khi mở ca.
2. Mở **Kế hoạch sản lượng**. Đọc giải thích từng món, tổng cả ngày và lịch đầu ngày/refill. Có thể sửa một lượng đúng bội số 4 trong công suất mẫu, ghi lý do rồi **Duyệt kế hoạch**. Ví dụ 48/52, không nhập 50 nếu mẻ là 4.
3. Nhấn **Xác nhận đã chuẩn bị**. App chỉ đưa lượng đầu ngày vào tồn lúc 08:00. Tổng kế hoạch là trần được duyệt; mẻ 14:00/17:00 chỉ được đặt khi nhịp POS đã quan sát lúc 12:00/15:00 cho thấy cần bổ sung. “Tổng đề xuất cả ngày” khác “Đã chuẩn bị đến hiện tại”.
4. Chạy đồng hồ hoặc chuyển đến 14:00/17:00 để xem mẻ thực đặt và sổ bán. Thử vào Giao dịch & theo dõi để kiểm tra số bán/tồn nguyên.
5. Tới **19:30**, mở **Giảm giá cuối ngày**. M1 V4 đánh giá tại 19:30, 20:00, 20:30, 21:00, 21:30. HOLD là giữ giá đang có, không tăng về niêm yết. Không có mức giảm mới thì không bắt buộc duyệt.
6. Muốn tự quyết: chọn **Manager tự quyết · Manual** ngay đầu trang, ghi lý do. Mở “Điều chỉnh của quản lý” ở từng món, chọn mức cần thiết. Chọn kênh **E-ink** cho sản phẩm trong quầy hoặc **tem** cho hàng đóng hộp phù hợp thực tế demo.
7. Nhấn **Duyệt thay đổi giá**, ghi lý do nếu khác gợi ý; sau đó **Áp dụng giá đã duyệt**. Duyệt chưa làm đổi giá. Sau Áp dụng mới đổi `price_version` và ghi `SIMULATED_ACK`.
8. Quy tắc: trần 40% trước 20:30, tối đa 50% từ 20:30, không tăng lại giá trong ngày, cách tối thiểu 30 phút, tối đa 2 lần đổi giá/SKU/ngày. Các trường hợp vi phạm bị chặn và lưu dấu vết; Manual không bỏ các ràng buộc này.
9. **Shadow** chỉ ghi thử quyết định, không đổi giá của giao dịch. Ba trang Tổng quan/Kế hoạch/Giảm giá dùng chung chế độ ca.
10. Tiếp tục từng checkpoint, duyệt/áp dụng hoặc từ chối có lý do. Tới 22:00 nhấn **Chốt ca**.
11. Vào **Báo cáo hiệu quả** và **Đối soát cuối ca**: chuẩn bị = bán + tồn; doanh thu phải khớp từng giao dịch. Manager xác nhận đối soát để lưu biên bản gắn checksum.
12. Mở **Giám sát hệ thống** xem DQ/sai số/drift/API/cảnh báo. Ca đang mở chưa có nhãn cả ngày nên không bịa accuracy. Một ngày ít mẫu chưa đủ để kết luận drift; nút “Tạo minh họa drift cô lập” dựng 28 ngày V4 có shock đánh giá riêng, không sửa tồn/giá/model ca.
13. Vào **Nhật ký quyết định** xem ai duyệt, khi nào và vì sao. Có thể quay lại lịch sử ca hoặc tạo kế hoạch ngày kế tiếp từ ca đã đóng.

### Mở lại một ca cũ

Nhấn Lịch sử ca từ trang Nhật ký/Báo cáo; chọn ca cần xem. Các ca V4 lưu trong `runtime/smartfresh_v4.sqlite3`. Dữ liệu cũ của prototype nằm trong database khác và không được nhập vào workspace V4.

## 4. Chatbot vẫn có, cấu hình như trước

Vào **Cài đặt AI**, chọn Gemini/OpenAI/Ollama; nhập model/API key của dịch vụ bạn có quyền dùng rồi **Kết nối & gọi thử AI**. Gemini có công cụ kiểm tra danh sách model trong phần cấu hình cũ khi phù hợp; đừng coi tên model mặc định là bảo đảm tài khoản được truy cập.

Copilot có vai trò giải thích, không quyết định thay Manager. Nó đọc `get_session_context`, `get_model_evidence` và `get_business_report`; không có công cụ duyệt, áp giá hay train. Nguồn số liệu là đúng ca V4 đang xem. Prompt/version/hash được hiển thị trong Cài đặt AI và mô tả ở `docs/COPILOT_V4.md`.

Chưa kết nối dịch vụ thì app và M1/M2 vẫn chạy; lời giải thích theo bằng chứng do máy chủ dựng vẫn có. Kiểm thử bàn giao đã thử luồng công cụ bằng phản hồi giả lập; không có API key của nhóm nên không gọi thực tế Gemini/OpenAI/Ollama hay khẳng định chi phí API bằng 0. Phí cloud tùy model/token và tài khoản; Ollama không có phí API cloud nhưng dùng tài nguyên máy.

## 5. Dữ liệu nào được dùng?

- Model/adapter/config: nguyên byte V4 trong bộ `Data (evaluated)/TRAINED_TESTED` được cung cấp; ba hash quan trọng ở `docs/MIGRATION_V4.md`.
- POS mô phỏng V3 chạy xuyên ngày từ **01/05/2022**, gồm giai đoạn validation tháng 5–6 và giai đoạn đánh giá sau test tháng 7–8. Mỗi ca lưu ngữ cảnh thị trường đầu ngày để tái lập; ca V2 cũ vẫn giữ phiên bản nguồn đã ghim.
- Lịch sử: quan sát trước ngày quyết định trong cùng bộ nguồn V4; ca tự chạy đã chốt có thể bổ sung lịch sử riêng, không dùng dữ liệu tương lai.
- Drift reference: feature **Fit** V4, 777 SKU-ngày, tới 30/04/2022. Chỉ dùng để giám sát, không làm target hay tune trong app.
- `reference/v4`: bảng kết quả V4 62 ngày và ledger của lượt đánh giá đã khóa, **chỉ đọc để tham chiếu**. Không đưa scorer/nhu cầu ẩn vào model input. Bộ kết quả tháng 7–8/2022 ghi đúng là **Post-Test Development Iteration**.

POS mô phỏng V3 sinh nhu cầu nền riêng theo SKU, có biến động qua ngày và giới hạn đỉnh cuối tuần quá lớn trong dữ liệu tham chiếu, sau đó thêm cơ hội mua nhạy giá khi đã áp dụng giảm giá. Worker chỉ trả sự kiện trong khoảng thời gian đã trôi qua. Các giới hạn cuối tuần, hệ số phản ứng giá và điều chỉnh khi baseline bị hết hàng là giả định của kịch bản, chưa được hiệu chỉnh bằng POS AEON. Nguồn Replay POS V4 vẫn dành cho việc đối chiếu ca cũ; không được coi là nguồn mua phát sinh liên tục. Một ca tương tác không phải chạy lại closed-loop test hoặc kết quả tham chiếu V4.

## 6. Nhập dữ liệu và lỗi thiếu/sai

Trong Dữ liệu đầu vào, tải mẫu History/Weather/Morning features V4/Transactions. Chọn ngày mục tiêu; tải CSV/XLSX/ZIP, xem trước lỗi/cảnh báo, sau đó mới xác nhận.

- Lịch sử phải trước ngày mục tiêu, đúng 7 SKU, số không âm; nên kèm `prepared_qty` và `censored_demand_flag` để dựng lag/censor V4. Không suy lượng cầu đầy đủ từ lượng bán đã hết hàng.
- Morning features: đủ 7 SKU không trùng, đúng ngày/cutoff 06:00 có múi giờ. Trường lag thiếu chỉ được nhận theo đúng cờ missing và giá trị fallback đã khai báo trong hợp đồng V4; không tùy tiện đổi mọi ô trống thành 0.
- Ngoài ngày mẫu: cần morning features đầy đủ và thời tiết có `issued_at`/nguồn/thời điểm sẵn có hợp lệ. App chặn nếu thiếu, không chuyển về data/model cũ.
- Khi tạo ca mô phỏng, chọn **Lấy thời tiết từ Open-Meteo** và nhập tọa độ cửa hàng. Với năm 2022, ứng dụng lấy mưa/nhiệt độ từ [Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api) của JMA GSM tại **độ trễ dự báo cố định 24 giờ**, có dữ liệu từ 2018. API không trả chính xác giờ công bố từng bản chạy; ứng dụng để `issued_at=null`, đánh dấu `vintage_verified=false` và chỉ cho mô phỏng. Từ giữa tháng 3/2024, ca lịch sử có thể dùng [Single Runs API](https://open-meteo.com/en/docs/single-runs-api) theo giờ khởi tạo model, nhưng giờ sẵn có thực tế vẫn là ước tính. Ca đang diễn ra chỉ dùng snapshot API chụp trước 06:00.
- File chứa nhãn/nhu cầu ẩn/tương lai bị cách ly. Thời tiết mẫu là dữ liệu ngày trước phục vụ mô phỏng; cảnh báo chưa xác minh forecast là thông tin nguồn, không phải lỗi tải model.
- POS mô phỏng V3 sinh lượt mua liên tục cho mọi ngày từ lịch sử có sẵn, không phụ thuộc file sự kiện từng ngày. Ca **01/07–31/08/2022** được chạy và chốt sẵn; mục **Báo cáo hiệu quả → Lịch sử theo ngày** hiển thị 62 ngày này khi mở ca **01/09/2022**. JOINT được đối chứng với baseline cùng thứ đã nhân ×10 trên đúng cùng POS; kết quả tại `docs/JOINT_TWO_MONTH_V3_EVALUATION.json` và `docs/JOINT_TWO_MONTH_AUDIT.md`. Bản Rolling-7 cũ là thử nghiệm bị loại vì baseline tự suy giảm khi hết hàng.
- Giao dịch nhập phải đúng SKU/phút ca, không vượt tồn. Tệp đã xác nhận cùng hash bị chặn nhập trùng.
- Sau lỗi hard rule, xem An toàn & sự cố để xử lý incident; không chỉ bấm đổi lại Assisted khi sự cố chưa đóng.

## 7. An toàn, monitoring và lifecycle

Thử lỗi M2 trên ca đang chờ duyệt; thử lỗi M1/tồn từ 19:30. App chuyển phương án thủ công và lưu incident. Trình tự phục hồi: gỡ cờ diễn tập → tiếp nhận → kiểm tra phục hồi → đóng sự cố → bật Assisted. Không sửa file model để demo lỗi; có nút diễn tập sẵn.

Trong Model Registry, **Tạo snapshot V4** lưu bản sao model/adapter/config có checksum. **Khôi phục V4** kiểm checksum snapshot rồi khôi phục đúng những byte đó, ghi người/lý do. Ca vẫn ghim V4; không đổi sang một model chưa được nhóm chốt. Snapshot không sao lưu database bán hàng; dùng công cụ backup SQLite riêng khi cần.

GO/NO-GO là đánh giá ca demo local, có thể còn PENDING trước khi chốt/xác nhận. Cảnh báo phục vụ/công suất theo ca được đọc riêng, không phải yêu cầu chọn lại model V4. Không coi GO local là đã kết nối production AEON.

## 8. Lãi góp và E-ink

Lãi góp mô phỏng = doanh thu thực ghi nhận − giá vốn V4 của **toàn bộ bánh đã làm** − phí hủy 150đ/bánh cuối ca − phí markdown của sổ ca. Giá vốn bánh dư đã nằm trong chi phí sản xuất, không trừ lần hai. Trước chốt, phí hủy còn chờ; không so lãi góp tạm giữa ca với lãi cả ngày.

App có hai kênh: tem giấy 350đ/lần đổi và E-ink 0đ/lần (xấp xỉ chi phí biên theo thông tin vận hành nhóm). Giá vốn/công suất/lead time còn là giả định của bộ dữ liệu, không phải chi phí AEON đã kiểm chứng. Adapter V4 vẫn quyết định với chi phí 350đ nguyên bản; đổi kênh hiển thị không sửa model/config hoặc tính lại bảng kết quả 62 ngày.

POS/E-ink ở prototype trả ACK mô phỏng, chưa gọi API AEON thật. Phương án tận dụng E-ink sẵn có không yêu cầu mua thêm màn hình cho prototype; tích hợp thực tế còn phụ thuộc hệ thống/quyền truy cập.

## 9. Kiểm thử và tệp trong gói

- `app.py`, `services/`, `web/`: app gốc được nối V4, các màn hình cũ và điều khiển vẫn có.
- `v4/`: adapter/bundle/config/lookup gốc. Không sửa nếu muốn giữ khóa.
- `simulation_only/v4/`: sự kiện thị trường Validation V4, chỉ worker mô phỏng đọc; không nằm trong feature input hoặc static web.
- `data/v4/`: mẫu đầu vào model và quan sát mới. Không còn `current_v9`, `v606`, `v607` hay LightGBM/XGBoost model cũ.
- `MODEL_DATA_HASHES.json`: hash model và dữ liệu được kiểm trước suy luận.
- `release_manifest.json`: checksum phần source/model/data phát hành.
- `docs/`: nguồn, đối chiếu thay đổi, QA, mô tả Copilot và hướng dẫn này.
- `tests/`: kiểm thử tích hợp. Chạy QA khi developer sửa app; người demo không cần chạy.
- `.github/workflows/ci.yml`: CI Linux/Windows, chưa có bằng chứng đã chạy trên GitHub của nhóm.

Muốn developer chạy lại kiểm thử app: cài `requirements-dev.txt`, chạy `python scripts/run_qa.py`. Đây là regression app, không train/tune/test lại mô hình kinh doanh.

Bản bàn giao đã kiểm tra trên Linux/Python 3.12; launcher CMD có trong gói nhưng chưa được thực thi trực tiếp trên máy Windows của bạn. Bằng chứng kiểm thử cụ thể nằm trong `docs/V4_QA_RESULTS.json` và `docs/V4_BROWSER_QA.json`.
