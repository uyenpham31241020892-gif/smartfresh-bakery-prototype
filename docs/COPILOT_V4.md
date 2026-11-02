# Copilot V4 — vai trò, nguồn, kiểm chứng và chi phí

Copilot là lớp giải thích bằng tiếng Việt trong giao diện prototype gốc. Nó không dự báo thay M1/M2 và không có quyền phê duyệt, sửa dữ liệu, áp giá, train/tune hoặc đổi model.

Prompt version: `SMARTFRESH_V4_COPILOT_2026_10_30`. Nội dung thực thi nằm trong `services/assistant.py`; SHA256 tính từ prompt thực đang chạy, hiện ở `/api/metadata` và Cài đặt AI. Model/provider là cấu hình của người dùng; lưu tên thực được trả về và response ID khi gọi thành công.

Nguồn: trạng thái ca V4 được chọn, bản kế hoạch, sổ giao dịch đã có, feature snapshot, dữ liệu báo cáo đúng phạm vi. Công cụ đọc: `get_session_context`, `get_model_evidence`, `get_business_report`. Không đọc file scorer/nhu cầu ẩn hay dòng khách tương lai.

Kiểm chứng: vòng hỏi đáp buộc dùng công cụ trước kết luận về ca. Các phần giải thích đề xuất/báo cáo có schema giới hạn lựa chọn fact và máy chủ chèn số liệu. Khi API thiếu key, lỗi hoặc trả sai định dạng, giữ lời giải thích từ bằng chứng và trạng thái lỗi; không bịa phản hồi LLM thành công. Chat tự do vẫn cần người dùng đối chiếu số trong bảng; gọi công cụ không bảo đảm mọi câu ngôn ngữ tự nhiên là đúng.

Chi phí: cloud theo model, lượng token và đơn giá tài khoản tại thời điểm dùng. App không tự gán một đơn giá hoặc báo tổng tiền chưa đo. Ollama chạy local không trả phí API cloud nhưng tiêu thụ tài nguyên máy. API key không nằm trong ZIP và không lưu vào audit. Không tự gửi tin nhắn cho thành viên nhóm.

Bằng chứng QA kiểm luồng công cụ bằng phản hồi mock để tránh gọi trả phí/đòi key. Kết nối thật cần người dùng bấm Kết nối & gọi thử AI bằng tài khoản được cấp quyền.
