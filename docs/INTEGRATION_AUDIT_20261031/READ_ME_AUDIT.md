# SmartFresh — Kiểm tra tích hợp V4, 31/10/2026

## Kết luận

**Bản app Châu gửi có lỗi tích hợp đầu vào M1. Đã sửa trong bản vá này. Chưa đạt tương đương toàn bộ quy trình đánh giá gốc.** Hash đúng chỉ chứng minh đúng file model; không chứng minh đúng trạng thái, feature, quy tắc vận hành và sổ tiền.

Sau sửa, phép kiểm soát cùng sản lượng và cùng chuỗi giá đã duyệt khớp runtime nguồn trên **60 ngày Validation, 420 SKU-ngày, 2.100 SKU-snapshot**. Tuy nhiên, app tương tác vẫn khác quy trình gốc ở quy tắc giá nền 21:00 và phí đổi giá thực thi. Bản vá không tự thêm một chính sách giảm giá vào ca rồi gọi đó là M1.

Model, adapter đã khóa và toàn bộ file data được giữ nguyên. Không train, tune, chọn ngày đẹp hoặc tăng khách để nâng kết quả.

## 1. Lỗi tích hợp đã sửa

| Điểm | App trước sửa | Runtime nguồn / bản vá |
|---|---|---|
| Tốc độ bán | Bán 60 phút / 60 | max(bán 30 phút / 30, bán 60 phút / 60) |
| Gia tốc bán | 2 × bán 30 phút − bán 60 phút; sai đơn vị | bán 30 phút / 30 − bán 60 phút / 60, đơn vị bánh/phút |
| Thời gian tồn đủ bán | Chia cho tốc độ 60 phút, ép tối thiểu 0,001 | Chia cho tốc độ chuẩn; khi tốc độ bằng 0 để missing cho preprocessor gốc xử lý |
| Dư dự kiến | Dùng tốc độ 60 phút | Dùng tốc độ chuẩn ở trên |
| Tồn kệ / kho | Tự chia lại từ tổng tồn ở mỗi lần dự báo | Theo dõi kệ/kho và chuyển bánh theo ngưỡng trong SKU master |
| Khách 30 phút | Số dòng giao dịch | Số customer_id riêng biệt đã mua; worker giữ ID sự kiện/khách và thứ tự giây gốc |
| Hết hàng 60 phút | Số phút suy ra từ thời điểm chạm tồn 0 | Với mô phỏng: tổng các khoảng 15 phút đã kết thúc có cờ hết hàng, đúng runtime nguồn |
| Prepared đầu vào M1 | Số đã sản xuất đến lúc đó | Tổng sản lượng đã cam kết, gồm các đợt refill; thường bằng nhau sau 17:00 |
| Giải thích tổng chi phí trên báo cáo | Hiện riêng chi phí sản xuất sau nhãn “tổng chi phí” | Hiện tổng chi phí sản xuất + hủy + đổi giá; số lãi góp không được sửa để đẹp hơn |

Ví dụ: bán 6 bánh/30 phút và 8 bánh/60 phút thì tốc độ đúng là 0,2 bánh/phút, gia tốc khoảng 0,0667 bánh/phút. App cũ đưa 0,1333 và 4 vào hai cột này. Cùng model nhưng đầu vào khác có thể cho dự báo khác.

Hàm tạo feature mới là bản sao nguyên byte `model_features.py` từ runtime gốc. Không dùng lại phép tính của app để làm oracle cho chính nó.

## 2. Kiểm chứng và phạm vi

- Tất cả **60 ngày có dữ liệu** từ 01/05 đến 30/06/2022; nguồn không có 04/05. Không tự bù dữ liệu.
- Khởi tạo mỗi ngày độc lập bằng cùng lịch sử quan sát quá khứ cho các nhánh. Không dùng kết quả của ngày tương lai. Đây **không phải** test cuốn chiếu 62 ngày tháng 7–8.
- 420 bộ feature/kế hoạch M2 được so với context sinh bởi POS nguồn: không lệch sau chuẩn hóa chú thích trống.
- 2.100 bộ feature M1 và hành động M1: không lệch trong phép kiểm soát chuỗi giá.
- 2.520 trạng thái SKU ở 5 checkpoint và 22:00: khớp prepared, sold, stock, revenue, shelf, backroom và lost.
- Phép kiểm soát chuỗi giá dùng runtime nguồn với **riêng khối giá nền 21:00 được bỏ trong bản chạy kiểm soát**, để cả hai phía thực sự cùng giá. Điều này được ghi rõ trong script, không phải chứng nhận toàn quy trình.
- Có một phép chạy riêng **runtime nguyên trạng**, bao gồm quy tắc 21:00, cho đủ bốn nhánh. Có cả bản tách riêng tracker từng nhánh và bản theo thứ tự runner chính thức; tổng kết quả hai cách trùng nhau trên 60 ngày này.
- 23.520 hàng thị trường: unit_events và response_multiplier khớp nguồn customer_events_ALL_PRIVATE. Không đổi luồng khách hay strength 0,6.
- Kiểm tra khóa hiện tại: 13/13 file giữ đúng hash của bản Châu gửi. Adapter, các bundle/model/config và các file trùng tên có nguồn đối chiếu hash trong provenance.json; bốn bảng dẫn xuất/đổi tên không được tuyên bố là bản sao nguyên byte chỉ dựa vào tên.
- 31 kiểm thử Python/API và contract; kiểm tra cú pháp JavaScript. Không có kiểm thử giao diện qua trình duyệt trong đợt này.
- Không báo MAE/RMSE từ lượng bán bị chặn bởi tồn hoặc từ doanh thu: chúng không phải nhãn cầu thật hay nhãn phản ứng giá phản thực. Kết quả ở đây là kiểm tra tích hợp và mô phỏng vận hành.

## 3. Những điểm còn khác quy trình gốc

**Giá nền lúc 21:00:** `pos_core.Session._enter_time` tự áp dụng `SIMULATED_PREAPPROVED_SELECTIVE_BASELINE_2100` cho mọi nhánh, kể cả JOINT. Có kiểm tra dư dự kiến, giá giảm tham chiếu theo SKU, giữ giá không tăng, rồi đưa mức sàn vào context. Sau đó M1 mới quyết định. Một số giá tham chiếu là giá tiền cụ thể, không nhất thiết thuộc thang phần trăm rời rạc của app. Vì vậy, đánh giá gốc là một quy trình có cả chính sách nền được duyệt trước, không đơn thuần là “AI M1 tự chọn toàn bộ giá”. App hiện yêu cầu duyệt Manager và chỉ có thang phần trăm; chưa tái hiện khối này.

**Chi phí thực thi:** runtime nguồn hạch toán phí đổi giá theo số price_version và thông số SKU. App giữ 350đ trong phép xét lợi ích của adapter nhưng hạch toán e-ink 0đ/lần, tem 350đ/lần. Phải cùng giả định phí mới so trực tiếp lãi góp được.

**Lịch sử nhiều ngày:** các ca kiểm tra ở đây khởi tạo độc lập. Một chuỗi tương tác dài, có Manager từ chối/đổi giá/đổi sản lượng, không thể được gọi là tái hiện toàn bộ chuỗi đánh giá gốc. Cần so từng ngày bằng đúng lịch sử đã chốt của từng nhánh. Không dùng kết quả một ngày để chứng minh toàn bộ chuỗi.

**Bộ đếm:** adapter gốc tăng đếm khi phát đề xuất thay đổi, không chờ Manager áp dụng. Bản vá giữ semantics này. Trong ca tương tác, từ chối đề xuất vẫn có thể tiêu hao lượt theo adapter; đây là giới hạn cần ghi nhận, không tự sửa model/policy đã khóa. Runner còn dùng tracker global khóa theo ngày/SKU; bản audit tách nhánh kiểm tra bổ sung và không thấy đổi tổng kết quả trên tập này, không suy ra mọi tập đều miễn nhiễm.

Do đó, có thể xác nhận phần mapping/trạng thái đã kiểm chứng trong điều kiện kiểm soát. **Không xác nhận “app đã khớp hoàn toàn, không có sai sót”.** Muốn app là bản tái hiện reference, cần triển khai minh bạch cả giá nền 21:00, giá tiền cụ thể và chính sách phí tương ứng; không gọi phần đó là đề xuất riêng của M1.

## 4. Kết quả runtime nguyên trạng, các nhánh tách riêng

Đơn vị tiền: VND; lượng: bánh. Mẫu: 60 ca độc lập/nhánh, 7 SKU/ca, 08:00–22:00, 5 checkpoint 19:30/20:00/20:30/21:00/21:30. Cùng sự kiện khách, strength 0,6, lịch sử nguồn trước từng ngày và cùng chính sách phí của runtime gốc.

| Nhánh | Doanh thu (đ) | Lãi góp trước chi phí cố định (đ) | Chuẩn bị | Đã bán | Dư/hủy cuối ngày |
|---|---:|---:|---:|---:|---:|
| BASELINE | 174.519.700 | 65.381.310 | 9.076 | 6.714 | 2.362 |
| M1_ONLY | 173.944.145 | 64.808.505 | 9.076 | 6.758 | 2.318 |
| M2_ONLY | 186.706.100 | 61.366.106 | 10.368 | 7.181 | 3.187 |
| JOINT_M1_M2 | 186.087.850 | 60.755.356 | 10.368 | 7.266 | 3.102 |

JOINT tăng doanh thu nhưng giảm lãi góp tổng và tăng hàng dư so với Baseline trên phép kiểm tra này. Không được dùng số này thay thế kết quả test tháng 7–8; kỳ đo, trạng thái khởi tạo và lịch sử khác nhau. Đây cũng không phải chứng minh hiệu quả thực tế tại AEON.

| Ngày | Nhánh | Chuẩn bị | Bán | Dư | Lãi góp (đ) |
|---|---|---:|---:|---:|---:|
| 2022-05-02 | BASELINE | 120 | 95 | 25 | 1.031.818 |
| 2022-05-02 | JOINT_M1_M2 | 152 | 109 | 43 | 953.056 |
| 2022-05-03 | BASELINE | 104 | 73 | 31 | 570.602 |
| 2022-05-03 | JOINT_M1_M2 | 124 | 76 | 48 | 185.788 |
| 2022-06-02 | BASELINE | 132 | 60 | 72 | -40.938 |
| 2022-06-02 | JOINT_M1_M2 | 156 | 65 | 91 | -339.626 |


Ngày 02/06, nguồn có 48 lượt mua nền trước 19:30, 12 lượt mua nền sau đó và 12 lượt nhạy giá tiềm năng sau 19:30. Kể cả toàn bộ lượt nhạy giá cuối ngày chuyển thành mua, tối đa là 72 bánh nếu không giảm trước 19:30. Chuẩn bị 156 bánh thì vẫn dư ít nhất 84 bánh trong kịch bản ấy. Thực tế app sau sửa bán 65, dư 91, lãi góp −337.526đ với e-ink; runtime đủ quy trình/chi phí cho JOINT là −339.626đ. **Sửa feature không làm biến mất việc sản lượng quá lớn so với nguồn cầu ngày này.**

Trước/sau sửa app trong cùng điều kiện cho 03/05: bán 73→76, dư 51→48 nhưng lãi góp 199.188→187.538đ. Bán thêm bằng giá thấp hơn vẫn có thể làm lãi giảm. Ngày 02/06: lãi góp −312.476→−337.526đ. Đây là bằng chứng rằng bản vá sửa tính đúng, không phải bản vá đảm bảo tăng chỉ số.

## 5. HOLD khi còn nhiều hàng có vô lý không?

Không vô lý về kinh tế: nếu giảm giá làm mất tiền trên những bánh vốn sẽ bán giá cao mà kéo thêm quá ít lượt mua, giữ giá có thể lãi hơn dù còn dư. Ví dụ giữ giá bán được 5 bánh × 25.000 = 125.000đ; giảm 50% chỉ bán được 8 × 12.500 = 100.000đ. Bán thêm 3 bánh và tiết kiệm 450đ phí hủy vẫn chưa bù doanh thu mất đi, chưa tính phí đổi giá.

Nhưng **logic có lý không đồng nghĩa ước lượng đúng hay policy tốt**. V4 dùng dự báo 30 phút và heuristic kéo đến cuối ngày; tỷ lệ kỳ vọng bán/tồn không phải xác suất bán hết đã hiệu chuẩn. Ngưỡng 88%, phần dư <1, cổng lợi ích >500đ và giới hạn hai lần là các thành phần policy đã khóa. Không có bảo đảm chúng tối ưu lợi nhuận từng ngày. Dự báo phản ứng giá sai hoặc thị trường mô phỏng quá khác phân phối huấn luyện sẽ làm quyết định yếu. Không thể chỉ nhìn tồn nhiều để kết luận bắt buộc giảm 50%; cũng không thể viện câu HOLD để bỏ qua sai số mô hình.

## 6. Cải thiện được gì mà không sửa data/model?

1. Dùng bản vá sửa feature/trạng thái; chốt một protocol trước khi chạy so sánh. Nếu mục tiêu là reference parity, bổ sung đầy đủ chính sách nền và phí nói trên, không chỉ sửa adapter input.
2. So bốn nhánh bằng cùng sự kiện khách và đúng lịch sử, giá hiệu lực, refill, phí; xuất cả ngày tốt lẫn ngày xấu. Không trộn đối chiếu Baseline nguồn với ca Manager đã thay đổi.
3. Với vận hành có Manager, có thể xây quy trình rà soát sản lượng/refill sớm và giảm/hoãn lô chưa sản xuất khi tín hiệu bán thực tế yếu, kèm lý do, quyền duyệt và audit. Đây là **quy trình vận hành bổ sung**, giữ nguyên model nhưng phải báo cáo riêng, không gọi là V4 tự động nguyên bản. Bản vá này chưa tự hủy các lô đã cam kết hay thay đổi chính sách M2.
4. Manager có thể điều chỉnh giá trực tiếp có lý do trong giới hạn hiện có; cần so riêng hiệu quả Manager+AI. Không sửa ngưỡng từ kết quả 60 ngày này rồi báo lại đây là đánh giá độc lập.
5. Xem doanh thu, lãi góp, hủy và mất bán cùng nhau. Doanh thu cao hơn có thể đi cùng lãi thấp hơn do sản xuất dư hoặc chiết khấu lớn. Mô phỏng ngày ít cầu không thể luôn thắng bằng thao tác kỹ thuật.

Không có cách trung thực để bảo đảm mọi ngày đều lãi và thắng Baseline nếu giữ nguyên cả nguồn khách, model và policy. Có thể cải thiện cách vận hành mà không retrain, nhưng hiệu quả phải được đo riêng; không được đổi khách/đáp ứng giá, giấu ngày lỗ hay bỏ chi phí để tạo số đẹp.

## 7. Áp dụng bản vá

Dừng app bằng Ctrl+C, sao lưu thư mục hiện tại, giải nén bản vá và chép đè các thư mục `services`, `web`, `tests`, `docs` cùng `release_manifest.json` vào đúng thư mục có `app.py`. Không cần cài lại môi trường hay thay model/data. Mở app, Ctrl+F5 và **tạo ca mới**.

Worker được sửa để giữ lại metadata sự kiện đã xảy ra nên hash triển khai mô phỏng thay đổi; hash file thị trường không đổi. Không tiếp tục ca cũ dưới hash mới; lịch sử cũ vẫn giữ lại để đối soát. Không xóa database/runtime.

## 8. Tái lập

Các script và output kèm trong thư mục này. Dùng Python 3.12, scikit-learn 1.9.1 và requirements của app; pytest/httpx cho test. Tạo cấu trúc thư mục audit riêng:

- `audit_app/SmartFresh_V4_Prototype/`: source đã áp dụng bản vá.
- `audit_original/Data (evaluated)/`: giải nén bộ evaluated Châu gửi, giữ nguyên cấu trúc TRAINED_TESTED.
- `audit_evidence/`: chép bốn script audit vào đây.

Chạy từ thư mục cha: `python audit_evidence/run_audit.py`, `python audit_evidence/run_reference.py`, `python audit_evidence/run_reference_isolated.py`. Các script tạo database tạm, không đụng dữ liệu ca đang dùng. `run_app_days.py` nhận đường dẫn source và đường dẫn JSON output để so bản cũ riêng 6 ngày đã chọn trước. Không chạy script này trên thư mục app đang phục vụ ca thật.

Trong thư mục app: `python -m pytest -q tests/test_m1_contract.py tests/test_v4.py`. Bộ test dùng database QA tạm và mật khẩu QA chỉ trong database đó, không sửa tài khoản phân phối.

Nguồn quyết định: `TRAINED_TESTED/smartfresh_adapter.py`; feature: `TRAINED_TESTED/SmartFresh_V609_03_TEST_POS_RUNTIME/03_TEST_POS_RUNTIME/code/model_features.py`; trạng thái/giá nền/phí: `pos_core.py` cùng thư mục; thứ tự bốn nhánh: `TRAINED_TESTED/run_official_test_62days.py`; sự kiện: `TRAINED_TESTED/customer_events_ALL_PRIVATE.jsonl`. Output chi tiết nằm ở JSON/CSV kèm theo.
