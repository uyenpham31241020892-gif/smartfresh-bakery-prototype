# Chỉ là trải nghiệm từ simulator
15.540 trạng thái thuộc 111 ngày nguồn × 7 SKU × 5 mốc × 4 giả định phản ứng giá. Không phải 444 ngày độc lập, không phải thử nghiệm tại AEON.
Nối ba bảng bằng sample_id. Features chỉ lấy allowlist m1_pre_action_columns; sample_id/scenario_id/source_date_group/decision_at/evidence_status dùng kiểm toán/nhóm, không làm predictor. Hành động là treatment, outcome là nhãn tương lai.
behavior_propensity là xác suất có điều kiện tại trạng thái của hành vi chọn đều trong tập giá khả thi; không phải xác suất thực của nhân viên AEON. Chỉ áp dụng trong simulator này. Stockout vẫn censor outcome.
Chia theo ngày gốc; mọi phiên bản một ngày đi cùng một fold. Không chọn nhãn “giá tối ưu” từ nhu cầu ẩn. Kiểm tra HOLD trong kịch bản null. Không được suy ra hiệu ứng giảm sớm thực tế từ các nhãn giả lập này.
