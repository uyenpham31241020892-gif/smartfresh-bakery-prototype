# SmartFresh V4 — gói làm việc sạch (frozen V4)

**Phiên bản chạy duy nhất:** V4 Profit-Maximizing. Baseline, dữ liệu fit/validation và POS được giữ nguyên; các script train thử nghiệm không tương đương đã được tách khỏi pipeline mặc định.

## Cấu trúc chính
- `ORIGINAL_BASELINE_PRIVATE/`: dữ liệu nguồn, baseline và tập test, không sửa.
- `TRAINED_TESTED/02_TRAIN_VALIDATION/` và `SmartFresh_V610_01_TRAIN_AUGMENTATION/`: dữ liệu train/validation/scenario cần thiết.
- `TRAINED_TESTED/train_v4_original_pipeline.py`: **khôi phục đúng thuật toán train từ ZIP ban đầu**, sửa đường dẫn và nhãn mô tả; **KHÔNG phải bằng chứng tự tái tạo chính xác trọng số V4**.
- `TRAINED_TESTED/agent_sandbox/`: **model M1/M2 chính thức V4 nguyên byte gốc**, adapter chính thức và policy phiên bản V4.
- `TEST_POS_RUNTIME/`: POS code/test/scorer; `run_official_test_62days.py` là runner.
- `TRAINED_TESTED/test_deliverables_v610_v4/`: KPI, ledger, báo cáo và evidence **bản V4 gốc** dùng làm nguồn chính.
- `EVALUATION_TABLES/`, `DOCUMENTS/`: phân tích, prototype và tài liệu dự án.

## Lệnh
Từ thư mục gốc này:

```bash
python run_v4_pipeline.py --test
python run_v4_pipeline.py --retrain-check
```

- `--test`: chạy trên bundle V4 frozen, ghi vào **thư mục output khác**, không ghi đè KPI gốc.
- `--retrain-check`: chạy thuật toán train được khôi phục; tự sao lưu/phục hồi bundle frozen trong `finally`. **Kết quả retrain chỉ để xác minh**, không thay file V4 dùng cho prototype.

## Ranh giới kết quả
- Đã chạy lại train của script khôi phục thành công (M2 34.965 mẫu); bundle tạo lại KHÔNG trùng SHA-256 với bundle V4 frozen gốc.
- Đã thử chạy lại POS với bundle frozen; bị giới hạn thời gian và chưa có scorer đủ 62 ngày trong môi trường này. **Không nhận là replay thành công**.
- KPI đóng gói là kết quả **bản V4 gốc**, không phải KPI của lần chạy chưa hoàn tất.
- Model gốc được lưu với scikit-learn 1.9.1, môi trường kiểm tra có 1.8.0 (cảnh báo tương thích). Để tái lập đúng nên sử dụng 1.9.1.
- V4 adapter dùng lag thô (không de-promo), Sell-out Gate >=88%, min gain 500, penalty 0,05.
- Dữ liệu test là mô phỏng và giá vốn là giả định, không phải kết quả POS thương mại AEON.

**Lưu ý:** Việc đổi nhãn tên/metadata không thể biến một bundle khác thành V4 đã kiểm thử. Hai `.joblib` frozen đã được giữ nguyên byte, kể cả metadata nội bộ (nếu có). Các thông số V4 thật nằm trong adapter và manifest.
