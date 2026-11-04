# Kiểm tra V4 sau khi phục hồi

1. **Sai sót trước:** `train_validate_export.py` (6.993 mẫu M2) không phải pipeline tạo bundle frozen và đã bị loại khỏi gói làm việc mặc định. Script train khác bị xóa nhầm đã được khôi phục dưới `train_v4_original_pipeline.py` (34.965 mẫu M2).
2. **Train thử được thực thi:** kết thúc mã 0, nhưng SHA-256 M1/M2 sau train khác SHA-256 của V4 frozen. Khác hash không tự chứng minh mô hình dự báo khác (metadata timestamp, sklearn version cũng ảnh hưởng), nhưng cũng không thể xác nhận tái lập chính xác.
3. **Test bundle gốc:** đã khởi chạy full test; mỗi lần bị cắt thời gian ở khoảng 30–34/62 ngày, nên không có scorer full. Các log thử nghiệm có trong `V4_EXECUTION_LOGS`.
4. **Đầu ra chính:** Giữ đúng V4 ledger, KPI và báo cáo từ ZIP gốc; không trộn KPI của các lần retrain.
5. **An toàn:** Không gỡ bỏ các input fit/validation/proxy, baseline, runtime, test scorer, adapter hoặc bundle frozen. `run_v4_pipeline.py --retrain-check` có khôi phục model nguyên byte.
6. **Bất biến:** POS và baseline đầu vào giữ nguyên; kết quả mô phỏng có thể khác vì mô hình/chính sách hoặc môi trường thư viện chứ không nhất thiết POS sinh một thị trường mới.
