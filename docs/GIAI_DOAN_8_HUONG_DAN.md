# SmartFresh — Giai đoạn 8: Evaluation, Reconciliation & Model Lifecycle

## Phạm vi và phần đã loại

Triển khai B09–B10 và F01–F03, F05–F08. **F04 (so sánh kinh doanh baseline vs M1+M2) không có trong giao diện GD8 theo yêu cầu.** Tab đối chiếu V9 cũ được gỡ. Các file nguồn/output V9 được giữ nguyên để bảo toàn dữ liệu lịch sử; API đọc reference cũ vẫn tương thích, không còn là tính năng hiển thị trên prototype.

So sánh model ứng viên với parent trên nhãn holdout phục vụ kiểm thử kỹ thuật vẫn có. Baseline dự báo đơn giản có sẵn trong luồng học dùng làm quality gate, không phải F04: không tạo bảng chứng minh lợi ích kinh doanh baseline vs M1+M2.

## Cập nhật nhanh từ GD7

1. Dừng server bằng Ctrl+C và sao lưu project, đặc biệt runtime.
2. Giải nén PATCH ra thư mục riêng. Copy nội dung vào project đang chứa app.py, gộp thư mục, thay file trùng tên. Không xóa project cũ.
3. Giữ nguyên .venv, .tools, .env, runtime, models và data. Patch không chứa những phần này, không chứa requirements hay launcher.
4. Khởi động lại Start-Gemini.cmd hiện có, Ctrl+F5 trên trình duyệt. Không cần tạo environment hay pip install lại.

Patch chỉ dành cho bản GD7 đã gửi. Nếu tự sửa code sau GD7, đối chiếu file trùng tên trước khi ghi đè. Dữ liệu SQLite cũ được giữ; schema mới chỉ thêm bảng model_holdouts và reconciliation_receipts. Full source là mã nguồn/model/data, không bao gồm environment, mật khẩu cấu hình hay database runtime cá nhân. Nếu muốn giữ phiên vận hành/tài khoản hiện tại, dùng patch trên project cũ.

## 1. Đối soát cuối ca — F01, F02, F03

Mở **Báo cáo hiệu quả**. Bảng mới lấy trực tiếp từ state và sổ giao dịch của ca đang chọn. Mỗi SKU kiểm tra:

- Chuẩn bị = đã bán + tồn cuối.
- Số đã bán trên báo cáo = tổng số lượng giao dịch của SKU.
- Doanh thu trên báo cáo = tổng thành tiền giao dịch của SKU.
- Mỗi giao dịch: thành tiền = số lượng × đơn giá; đơn giá khớp giá tham chiếu và mức giảm được ghi trong giao dịch.
- SKU phải nằm trong danh mục ca; số lượng và số tiền phải hợp lệ, không âm.

Đang vận hành: PROVISIONAL, chưa công bố KPI cuối ca. Ca đóng và khớp: RECONCILED. Có bất kỳ lỗi nào: MISMATCH, kpis=null, chặn xác nhận. Kiểm tra nâng cao còn chạy trước khi đóng ca nên một dòng tiền sai vẫn bị chặn dù tổng doanh thu tình cờ khớp.

GD8 cũng chặn thẻ KPI của ca có mismatch và loại ca đó khỏi tổng KPI kinh doanh/accuracy trong Monitoring, đồng thời giữ cảnh báo và bằng chứng sai lệch. Không tự sửa số liệu cho khớp. Chỉ sửa qua quy trình nghiệp vụ có căn cứ; prototype không có chức năng chỉnh sổ đã khóa.

**Manager xác nhận đối soát:** nhập lý do, backend kiểm tra revision và SHA256 state. Hệ thống lưu ngày kiểm tra, model, từng dòng đối soát, kết quả, người xác nhận và lý do trong biên bản SQLite + audit. Bấm lặp cùng snapshot trả biên bản cũ, không tạo hai bản. Snapshot thay đổi thì xác nhận cũ không còn được ghi là hiện hành. Việc xác nhận không sửa sổ hoặc tăng revision của ca.

Lưu ý: trong prototype, tồn cuối ca được quy ước là waste/hàng dư; chưa phải chứng từ hủy vật lý đã ký. Muốn tích hợp AEON cần adapter kiểm kê, điều chuyển và chứng từ hủy thực tế.

## 2. Chất lượng phục vụ và contribution — F05, F06

Báo cáo giữ lost sales và stockout bên cạnh waste:

- Simulation: lost sales đọc từ lượt mua không được đáp ứng do simulator tạo. Đây là số mô phỏng, không phải khách thực tế.
- Live: lost sales là chưa quan sát, không suy ra bằng 0 từ doanh số bán.
- Stockout SKU-ca: số SKU tồn cuối bằng 0. Đây là proxy, không phải số phút hết hàng hoặc toàn bộ lượt hết hàng giữa ca.

Contribution trước overhead = doanh thu đối soát − giá vốn sản xuất giả định.
Giá vốn hiện dùng = tổng lượng chuẩn bị × 45% giá tham chiếu, làm tròn từng SKU. Tính cả hàng đã sản xuất nhưng không bán. Chưa trừ nhân công, điện, thuê mặt bằng, vận chuyển, thuế/phí; không gọi là lợi nhuận ròng. Nếu doanh nghiệp cấp giá vốn thật, cần thay giả định bằng dữ liệu có nguồn.

## 3. Sensitivity Analysis — F07

Sau khi đóng ca và đối soát khớp, nhấn **Độ nhạy phản ứng giá**.

Đọc model M1 đã ghim ở ca, chỉ xem quyết định có status=applied; bỏ shadow. Với từng snapshot giá/tồn, nhân phản ứng tăng thêm dự báo với 0,5× / 1× / 1,5× và chặn số lượng theo tồn snapshot. Không sửa quyết định hoặc model.

Các cột là tổng đáp ứng cục bộ và giá trị đáp ứng cục bộ. Vì nhiều snapshot có thể cùng dùng một lượng tồn, không được coi tổng này là doanh thu cả ca, uplift đã đo hoặc hiệu quả nhân quả. Đây là stress test phản ứng giá ở chính sách cố định; không tái chạy toàn bộ mô phỏng, không có so sánh baseline và không tối ưu lại lịch giá. Model không xác minh được thì từ chối phân tích, không bịa phản ứng.

## 4. Model Registry — B09

Mở **Model Registry**, tách khỏi Dashboard Tổng quan. Có:

- Bản frozen, các ứng viên thật/demo và cờ phiên bản đang dùng.
- Parent, trạng thái quality gate, nguồn, train/calibration/test, metric parent/ứng viên.
- Manifest SHA256; kiểm tra checksum artifact thực tế khi đọc, kể cả engine từng được cache.
- Kiểm tra tương thích SKU, cấu hình policy, schema M1 và schema M2 cho phép.
- Kết quả fresh holdout và lịch sử promotion/rollback, người thực hiện/lý do đối với sự kiện mới GD8. Sự kiện cũ không được tự gán người duyệt mới.

Registry không có upload artifact tùy ý hoặc xóa model. Ứng viên được tạo qua luồng huấn luyện LightGBM hiện có trong **Học từ dữ liệu**.

## 5. Huấn luyện và đánh giá ứng viên

Luồng hiện có vẫn hoạt động: nạp daily outcomes/promo trials → kiểm tra schema, issued_at, trùng/xung đột → dựng feature quá khứ → train, calibration và test theo thời gian → lưu model/version/report.

M2 cần tối thiểu 63 ngày liên tục, đủ SKU; lịch sử 35 ngày, nhãn nhu cầu chỉ dùng ngày không hết hàng, còn hàng và không bán giảm giá. M1 cần ít nhất 42 ngày, đo controlled_increment có experiment_id và phủ SKU/slot/mức giảm. Doanh số thô không phải nhãn phản ứng giá.

Ứng viên phải qua các gate sẵn có: cải thiện MAE, không kém dự báo đơn giản, không suy giảm SKU quá ngưỡng, kiểm tra loss sản lượng M2. Đây là các gate prototype, chưa là tiêu chuẩn doanh nghiệp. Dữ liệu demo luôn demo_only và không được đưa vào vận hành thật.

## 6. Fresh Holdout — F08

Trong registry, chọn **Kiểm tra 7 ngày holdout mới** sau khi nạp dữ liệu kết quả mới vào nguồn tương ứng.

- Cần 7 ngày liên tục sau mốc train/test và các holdout đã dùng cùng loại model/nguồn. Các quan sát đã dùng không được dùng lại để chọn ứng viên.
- M2 cần đủ SKU mỗi ngày, tối thiểu 5 nhãn hợp lệ/SKU và lịch sử liên tục 35 ngày trước từng ngày dự báo. Ngày bị stockout/discount được giữ làm lịch sử, không dùng làm nhãn nhu cầu.
- M1 cần độ phủ các tổ hợp SKU/slot/mức giảm hợp lệ và nhãn controlled_increment đã được ingestion kiểm tra.
- Model parent và ứng viên được xác minh checksum/tương thích. Không fit, không cập nhật offset hay trọng số từ holdout.
- Đánh giá walk-forward một ngày: khi dự báo ngày D chỉ đọc lịch sử < D. Kết quả ngày trước trong cửa sổ được phép làm lịch sử cho ngày sau; không phải forecast cố định bảy ngày cùng lúc.
- Lưu SHA256 dữ liệu đánh giá, khoảng ngày, số dòng, MAE/WAPE/Bias của hai phiên bản, người chạy và kết quả gate. WAPE/Bias có actual tổng bằng 0 thì N/A.
- Gate fresh của prototype: MAE ứng viên ≤ MAE parent × 1,10 + 0,5. Đây là ngưỡng minh họa có ghi trong bằng chứng, chưa được hiệu chỉnh cho AEON. Holdout mới nhất FAIL chặn promotion; không tự đổi model khi PASS.
- Chưa có dữ liệu mới thì báo thiếu, không tạo điểm giả. Đánh giá ban đầu vẫn được lưu riêng; fresh holdout sau đó là kiểm tra bổ sung. Mô hình frozen không được gán điểm từ dữ liệu ứng viên không liên quan.

Ngày đã dùng fresh holdout cũng bị loại khỏi test của lần train tiếp. Ca mới dùng phiên bản đã kiểm tra phải nằm sau mốc đánh giá của phiên bản đó; tránh trình bày dự báo quá khứ như một quyết định chưa thấy kết quả. Các ca đã tạo vẫn giữ nguyên trạng thái/phiên bản.

## 7. Promotion và rollback — B10

Chỉ Manager được gọi API đổi model. Promotion cần lý do và expected_active chính xác; report phải là real, đạt gate, chờ xác nhận, có parent đúng phiên bản đang dùng. Checksum model/training snapshot và tương thích được kiểm tra lại tại lúc duyệt. Nếu fresh holdout mới nhất FAIL thì bị chặn. Không có thao tác tự promotion của AI chat.

Thành công: cập nhật con trỏ model_active trong transaction, lưu audit người duyệt/lý do/from/to. Ca tạo sau dùng model mới; ca đang chạy giữ model đã ghim. Chính sách M1, M2 không tự đổi theo tên phiên bản.

Rollback: Manager nhập lý do → kiểm tra expected_active → tìm parent trong registry đã lưu (vẫn phục hồi được nếu thư mục artifact active bị mất) → xác minh artifact parent và nạp được → đổi con trỏ trong transaction → lưu audit. Không ghi đè artifact và không sửa sổ giao dịch của ca cũ. Nếu parent thiếu/hỏng, rollback từ chối, không tuyên bố phục hồi thành công.

Rollback thật cần có ứng viên dữ liệu thật đủ điều kiện đã được promotion. Khi chỉ có frozen/demo, không tạo một nút rollback thành công giả; vẫn có rollback drill GD6 trong An toàn & sự cố. Các kiểm thử tự động GD8 thực hiện promotion/rollback thật trên database tạm, không đổi model workspace của bạn.

## Kịch bản demo 8 phút

1. Mở ca chưa đóng → Báo cáo: PROVISIONAL, chưa xác nhận.
2. Duyệt sản lượng, chuẩn bị, xử lý đủ năm mốc giá, đến 22:00 và chốt.
3. Báo cáo: xem từng SKU và tổng tiền từ sổ; xác nhận bằng Manager.
4. Mở sensitivity: so ba hệ số; giải thích đây là giả định cục bộ.
5. Model Registry: bản đang dùng, checksum/parent/lịch sử.
6. Học từ dữ liệu → Thử luồng bằng dữ liệu demo → quay Registry: có model đã train thật nhưng demo_only, không được promotion.
7. Bấm fresh holdout khi chưa nạp ngày mới: hệ thống báo thiếu đúng điều kiện.
8. Đọc các bằng chứng tự động trong GD8_RELEASE_CHECKS.json: test promotion/rollback trên dữ liệu tổng hợp trong DB tạm, không phải nghiệm thu với dữ liệu AEON.

## API mới

GET /api/evaluation/{sid}; POST /api/evaluation/{sid}/certify (revision, state_sha256, reason); GET /api/evaluation/{sid}/sensitivity; GET /api/registry; POST /api/learning/{version}/holdout.

Các endpoint promote/rollback hiện có được giữ, bổ sung kiểm tra và audit. GET dành cho tài khoản đã đăng nhập; POST chứng nhận, holdout và đổi model cần Manager. Không thêm dependency và không đổi launcher.

## Giới hạn kiểm chứng

Kiểm tra Python/API và tương tác DOM có chạy. Chưa chạy launcher trực tiếp trên Windows hoặc kiểm tra ảnh giao diện bằng browser đồ họa trong môi trường này. Chưa có dữ liệu/quyền AEON để nghiệm thu financial ledger, nhu cầu mất thật, phản ứng giá causal hoặc fresh holdout doanh nghiệp. Không gọi kết quả tổng hợp trong kiểm thử là kết quả của cửa hàng thật.
