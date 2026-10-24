# SmartFresh GD7 — Monitoring & Drift Dashboard
Nhóm D01–D09 · 22/10/2026

## 1. Nâng cấp bằng PATCH — giữ nguyên environment của bạn
Nếu đang dùng **SmartFresh GD6 Safety, Incident & Fallback** đã bàn giao, dùng **SmartFresh_GD7_PATCH_Only.zip**:
1. Dừng server cũ bằng Ctrl+C và đóng cửa sổ chạy app.
2. Sao lưu thư mục dự án cũ của bạn.
3. Giải nén patch ra một thư mục riêng. Copy các file và thư mục bên trong vào **đúng thư mục GD6 có app.py**. Chọn thay thế các file trùng, gộp các thư mục; không xóa cả services/web cũ.
4. Giữ nguyên **.venv, .tools, runtime, .env, models, data** trên máy bạn. Patch không chứa và không ghi đè những thư mục/file đó.
5. Mở lại Start-Gemini.cmd như trước, dùng đúng thư mục dự án cũ. Launcher sẽ dùng environment đã có. GD7 không thêm thư viện runtime; không cần tạo venv mới hoặc chạy pip chỉ để nâng cấp này.
6. Mở lại trình duyệt, nhấn **Ctrl+F5** một lần để lấy JS/CSS mới. Đăng nhập bằng tài khoản cũ; phiên đã hết hạn thì đăng nhập lại, không phải tạo lại Manager.
7. Menu trái có mục **Giám sát hệ thống**. Các bảng monitoring được thêm tự động vào SQLite hiện tại, không xóa ca, giao dịch, tài khoản hay model đang dùng.

Patch dành cho bản GD6 của cuộc trò chuyện này, không áp thẳng lên GD4/GD5 thiếu auth/safety. Nếu đã tự sửa app.py/web/app.js, hãy đối chiếu trước khi chép đè để không mất sửa đổi riêng. Không chép patch vào thư mục cha bên ngoài app.py.

**Bản full** dùng để giải nén dự án mới hoặc làm bản sao hoàn chỉnh: có các chức năng trước đây, GD5, GD6, bản sửa launcher và GD7. Không đóng gói .venv hoặc database phiên cũ. Muốn giữ environment/tài khoản thì dùng patch tại đúng thư mục cũ.

## 2. Trang mới được chia như thế nào?
Tổng quan chỉ có một thanh nhỏ dẫn sang giám sát; không nhồi toàn bộ bảng mới vào dashboard chính.

Trang Giám sát gồm bốn tab:
| Tab | Nội dung thực sự tính từ dữ liệu |
|---|---|
| Dữ liệu | DQ ca hiện tại, freshness từng SKU, cutoff forecast, nguồn bán, lượt nhập/cách ly/trùng; PSI/KS feature |
| Mô hình | WAPE/MAE/Bias theo model và loại nhãn, biểu đồ theo ngày, performance drift, lát cắt SKU/ngày/thời tiết |
| Vận hành | HTTP latency/status/request ID, job local, M1 hard rules, luồng duyệt/override và guardrails kinh doanh |
| Cảnh báo | Điều kiện đang còn, bằng chứng, tiếp nhận có danh tính, lịch sử điều kiện đã hết |

Có bộ lọc ngày ca, SKU, mode, model và nguồn phân tích. Nguồn **runtime** là các ca đã lưu; nguồn **sandbox** là minh họa cô lập. Không trộn các phiên bản model/nguồn nhãn thành một điểm tổng. Các bảng luôn ghi phạm vi riêng: DQ thuộc ca đang chọn, API thuộc workspace 24 giờ theo thời gian máy.

Nút Làm mới và tùy chọn làm mới 30 giây không tự chạy model huấn luyện hoặc thay đổi giá.

## 3. Tại sao lúc mới mở chưa có WAPE?
Chưa chốt ca thì chưa biết actual của cả ngày, nên GD7 không hiển thị 0% hay tự đọc nhu cầu ngày mai để lấp số.

Sau khi chốt một ca qua app, nhãn đánh giá được lưu vào bảng monitoring riêng. Ca mô phỏng cũ có thể tái lập sau chốt nếu phiên bản/hash simulator vẫn phù hợp; nếu không tái lập được thì báo thiếu, không dùng số bán để thay thế nhu cầu.

Các dòng này chỉ phục vụ **đánh giá sau chốt**, không được đưa lại vào feature M2 hoặc tập huấn luyện tự động. Việc xem dashboard không làm thay đổi state/revision của ca.

## 4. WAPE, MAE và Bias được tính ra sao? — D02
Với forecast p và actual a:
- WAPE = tổng |p − a| / tổng a × 100%.
- MAE = trung bình |p − a|, đơn vị bánh.
- Bias = tổng (p − a) / tổng a × 100%. Dương là dự báo cao hơn actual; âm là dự báo thấp hơn.

Nếu tổng actual bằng 0, WAPE/Bias là **N/A**, không tự đặt bằng 0. MAE vẫn tính được nếu có dòng hợp lệ.

Ví dụ dự báo [12, 0], actual [10, 2]: tổng lỗi tuyệt đối là 4, tổng actual là 12 → WAPE 33,33%, MAE 2 bánh, Bias 0%.

Không dùng “100 − WAPE” rồi gọi đó là accuracy. Mục tiêu 18% trong dự án là mục tiêu học thuật, chưa phải SLA vận hành.

### Ba nhóm không được nhập làm một
1. **synthetic_base_demand:** ca mô phỏng đã chốt; actual là lượt mua gốc (không phải lượt mua khuyến mãi) của simulator đúng seed/version. Đây không phải POS AEON.
2. **observed_sales_proxy:** ca dữ liệu nhập; actual là số bán đã ghi nhận. Hết hàng có thể làm số bán thấp hơn nhu cầu, còn khuyến mãi có thể thay đổi cấu phần nhu cầu. Vì vậy chỉ gọi là sai số so số bán quan sát, không kết luận đó là lỗi nhu cầu gốc.
3. **RULE_ROLLING7:** đề xuất từ fallback được giữ riêng khỏi AI_M2, dù cùng ghi version model của ca.

Sandbox có loại nhãn riêng **controlled_synthetic_demand**, không nhập vào runtime. Model mới và model cũ cũng có nhóm riêng.

Lát cắt theo SKU, ngày thường/cuối tuần/ngày lễ, mưa/khô dùng cùng công thức trên đúng tập con. “Mưa” ở đây là forecast rain > 0, không phải thời tiết quan sát đã được xác minh.

## 5. Data drift — D03
GD7 đọc baseline feature từ M2_Training_Matrix của V9, chỉ dòng TRAIN đến ngày khóa huấn luyện. Hash của file được đối chiếu provenance. Chỉ lấy các feature cho phép; không đọc cột target/hidden để làm drift feature.

So các feature như lag1/lag7 sales, rolling7/rolling14, độ biến động bán và forecast mưa. Nếu cột nhiệt độ không có trong reference thì không tự điền 0; dòng đó chưa đủ reference để đánh giá.

Window hiện tại là tối đa **7 ngày có feature gần nhất** trong bộ lọc, cùng model và nguồn AI_M2. Baseline là reference TRAIN phù hợp, không lấy toàn bộ test làm chuẩn. Với model học mới chưa đăng ký reference tương thích, hệ thống ghi “reference chưa sẵn có”, không tự so với V9 rồi kết luận drift.

- **PSI:** phân bố theo bins từ reference, làm trơn pseudocount 0,5 để xử lý bins rỗng. Giá trị lớn hơn cho thấy phân bố khác hơn, không chứng minh nguyên nhân.
- **KS statistic:** khoảng cách lớn nhất giữa hai phân bố tích lũy. Chỉ trả statistic, không gắn p-value hoặc tuyên bố có ý nghĩa thống kê.
- Tối thiểu 30 dòng và 5 ngày hiện tại mới bật đánh giá theo ngưỡng. Có 40 ca thử cùng một ngày vẫn chỉ là một ngày, không tự thành bằng chứng nhiều ngày độc lập.

Mặc định workspace **chưa đặt ngưỡng PSI/performance drift**. Vẫn xem được chỉ số và trạng thái “Chưa đặt ngưỡng”. Manager có thể đặt ngưỡng local cùng ghi chú hiệu chỉnh; có version/audit và chống ghi đè từ cấu hình cũ. Đây là cấu hình thử nghiệm, không phải chuẩn production tự công nhận.

## 6. Performance drift — D04
So WAPE của tối đa 7 ngày có nhãn gần nhất với tối đa 7 ngày ngay trước đó. Hai cửa sổ không chồng nhau và phải đủ mẫu/ngày, cùng model, AI_M2 và loại nhãn nhu cầu.

Delta được tính bằng **điểm phần trăm**: từ WAPE 12% lên 20% là tăng 8 điểm %, không gọi là tăng 8% tương đối.

Không tự dùng observed-sales proxy để kết luận performance drift của nhu cầu gốc. Nếu mới có một ca, thiếu hai cửa sổ hoặc mẫu số bằng 0, trạng thái là chưa đủ dữ liệu. Không so điểm của model A với model B rồi gọi đó là performance drift của cùng model.

## 7. M1 safety và phê duyệt — D05/D08
GD7 kiểm tra các dòng đề xuất và các quyết định thực sự có status applied:
- Discount có nằm trong ladder không?
- Có tuân thủ cap/floor theo mốc thời gian không?
- Có giảm ngược so mức trước không?

Ba số được tách rõ:
1. Vi phạm ở đề xuất.
2. Vi phạm ở quyết định **đã applied**.
3. Số incident HARD_RULE_BLOCK đã ghi, có thể đã được backend chặn từ trước.

Incident được GD6 khử trùng khi chưa đóng, nên đây không phải số mọi lần bấm sai. Shadow không tính là applied. Chưa có dòng applied thì ghi chưa có, không dùng “0 vi phạm” để ám chỉ đã có nhiều quan sát.

Workflow có số kế hoạch/giá đang chờ, approved chưa áp dụng, các lượt duyệt/từ chối và override. Override chỉ đếm khi số lượng/mức giảm được duyệt thật sự khác đề xuất, không đếm chỉ vì có ghi lý do. Số workflow là theo ca, không phải số SKU.

## 8. API và job monitoring — D06
Middleware đo request thực của API local:
- Tổng request, số 4xx và 5xx, p50/p95 theo route.
- Thời gian là backend tới response headers, chưa phải độ trễ mạng/POS đầu cuối.
- Response có X-Request-ID; bảng lỗi có request ID để lần ngược.
- Không lưu body, query string, mật khẩu hoặc API key. Route được chuẩn hóa, không ghi nguyên URL chứa tham số.
- GET snapshot giám sát thành công bị loại để polling không tự làm lệch mẫu; thao tác tạo sandbox/cấu hình/ack vẫn ghi HTTP.
- Tối đa 20.000 request gần nhất, xem cửa sổ 24 giờ **thời gian máy**, không phải ngày ca năm 2022.

Job local được ghi lúc chạy: huấn luyện model, tạo sandbox và ghi đánh giá sau chốt. Trạng thái succeeded/rejected/failed/interrupted được tách riêng. Một ứng viên model không đạt chỉ tiêu vẫn có thể là job tính toán chạy thành công. Nếu server khởi động lại mà job cũ còn running, nó được đánh dấu interrupted, không tự gọi là thành công.

Lỗi đồng hồ mô phỏng đã có ở GD6 cũng được hiển thị. GD7 không dựng một queue worker hoặc service cloud giả để đếm job.

## 9. Business guardrails — D07
Chỉ tính từ ca đã chốt: prepared, sold, waste, waste rate, revenue và số SKU-ca có tồn cuối bằng 0.
- Ca mô phỏng và ca nhập giữ thành nhóm riêng.
- Tồn cuối bằng 0 là chỉ báo stockout cuối ca; không chứng minh thời lượng hết hàng.
- Lost sales chỉ có số từ simulator. Với ca nhập, ghi **chưa biết**, không gán 0.
- Nếu sổ Prepared/Sold/Stock hoặc tổng tiền ledger không khớp, tạo cảnh báo đối soát; không tự sửa ledger.
- Một ngày có thể có nhiều seed/ca thử. Tổng các ca không phải doanh thu duy nhất của một quầy trong tháng.

GD7 không bịa baseline đối chứng cho ca hiện tại. Đối soát/lifecycle/holdout đầy đủ vẫn thuộc giai đoạn sau.

## 10. Cảnh báo và tiếp nhận
Cảnh báo có bằng chứng, thời gian thấy đầu/cuối, trạng thái điều kiện còn/hết và người tiếp nhận. Có thể phát hiện model hash lỗi, feed stale, incident còn mở, applied hard-rule violation, lỗi API/job, đối soát, WAPE vượt mục tiêu học thuật và drift theo ngưỡng local đã đặt.

**Tiếp nhận** chỉ nghĩa người quản lý đã đọc và ghi chú; không làm biến mất vấn đề, không đóng incident và không bật lại AI. Backend kiểm evidence hash: bằng chứng đã thay đổi thì không nhận xác nhận cũ. Nếu số liệu mới thay đổi, acknowledgement cũ được gỡ để cần xem lại. Khi điều kiện hết trong lần đánh giá tiếp theo, cảnh báo được đánh dấu đã hết và giữ lịch sử.

Các phạm vi source/ngày/SKU/model có lịch sử cảnh báo riêng, để chuyển bộ lọc không vô tình đóng cảnh báo của phạm vi khác. Dashboard không phải một daemon cảnh báo 24/7; điều kiện được đánh giá khi mở/làm mới trang/API. Có link sang An toàn & sự cố để xử lý GD6. Không gửi thông báo ra ngoài, không tự tạo incident từ PSI chưa hiệu chỉnh, không tự dừng AI/retrain/rollback.

Manager được tạo sandbox, lưu ngưỡng và tiếp nhận. Staff/Viewer xem được giám sát nhưng các API thay đổi này vẫn bị chặn 403. Các tài khoản/quyền GD6 được giữ nguyên.

## 11. Thử ngay mà không phải chốt 14 ngày
1. Đăng nhập Manager, mở Giám sát hệ thống.
2. Bấm **Tạo minh họa drift cô lập**.
3. Prototype chạy M2 thật cho 28 ngày synthetic với lịch sử chỉ đến ngày trước. Sau khi dự báo ngày 22 trở đi, actual được tiêm shock nhu cầu 2,5x có kiểm soát; các ngày đã hoàn thành mới cập nhật lịch sử của sandbox cho ngày sau.
4. Tab Mô hình có WAPE/MAE/Bias, biểu đồ và hai cửa sổ performance. Tab Dữ liệu có PSI/KS.
5. Tab Cảnh báo có data/performance drift để thử tiếp nhận và mở bằng chứng.
6. Đổi Nguồn phân tích về **Các ca vận hành local** để trở lại dữ liệu thật của workspace.

Ngưỡng sandbox cố ý là PSI 0,2 và delta WAPE 5 điểm % để diễn tập; được ghi rõ chưa hiệu chỉnh và không thay cấu hình workspace. Sandbox không tạo ca bán, không có doanh thu/tồn kho giả, không đổi active model hay tập học. Trạng thái/revision/giá của ca đang dùng giữ nguyên.

Đây không phải kết quả tái lập độc lập của thí nghiệm V9 tháng 9 và không phải dữ liệu vận hành AEON. Chỉ minh họa dashboard phản ứng khi môi trường thay đổi.

## 12. Kiểm thử và bàn giao
- Bộ hồi quy: **128 bài pass**, gồm kiểm tra nâng cấp; kết quả ghi trong GD7_RELEASE_CHECKS.json.
- Các test mới kiểm công thức, mẫu số 0, PSI/KS hằng/shift, không nhìn nhãn ngày đang mở, tách proxy/fallback/AI, cache đánh giá, reference allowlist/hash, filters, slices, alert ack/version, HTTP lỗi thật, job trạng thái và quyền.
- DOM chạy đủ 4 tab, biểu đồ, cảnh báo drift, form ngưỡng, tiếp nhận và Staff read-only; không có lỗi JS, không đổi ca khi tạo sandbox.
- Có script `python scripts/demo_gd7_check.py`: dùng database tạm để đi hết authenticated API, chốt ca, xem metric, tạo minh họa và thử quyền Viewer. Không yêu cầu cài thêm package runtime.
- Chạy pytest cần requirements-dev đã có, không phải bước bắt buộc để chạy dashboard.
- Không có xác nhận trực tiếp Windows CMD/visual QA bằng trình duyệt đồ họa trong môi trường này. DOM/API không thay thế kiểm tra bố cục trên máy bạn.

Giới hạn đọc: 500 ca mới nhất theo bộ lọc, 1.000 lượt nhập, 20.000 event audit/HTTP để tránh đọc vô hạn. Có thông báo khi ca/audit bị giới hạn; có thể thu hẹp bộ lọc. Chưa có tracing/metrics tập trung, dữ liệu reference sản xuất hiệu chỉnh, SSO/POS thật hoặc cảnh báo nền ra ngoài.
