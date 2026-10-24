# Current: V606 service2130 v2

See [current guide](V606_SERVICE2130.md). Original prototype at http://127.0.0.1:8000. Start a NEW session for the changed supply policy; older sessions are preserved. Sections below describe earlier iterations.

# V6.06 trong prototype

Chạy **Start.cmd**, mở **http://127.0.0.1:8000**. Giao diện prototype giữ nguyên: duyệt kế hoạch M2, xác nhận chuẩn bị, POS backend tự sinh giao dịch và cập nhật tồn; M1 tự tạo đề xuất tại checkpoint. Không cần mở trang POS riêng hoặc nhập token POS. Lần đầu trên database mới cần tạo tài khoản Manager bằng mật khẩu tự chọn.

Ngày mặc định là **01/07/2022**, thuộc kỳ test. Model lấy từ ZIP Train_Validation_Results: M2 XGBoost cùng preprocessor và M1 RandomForest bắt chước hành động. Không dùng model V9, không retrain và chặn API ghi vào luồng learning trong lúc chạy test. Đầu vào chỉ theo feature contract; không dùng dữ liệu private, nhãn tương lai hoặc kết quả so sánh làm feature.

POS mặc định dùng **kịch bản thử tải đông khách 4× trung bình bán quan sát trước test**, seed cố định, phân bố lượt mua trên giờ mở cửa. Đồng hồ mặc định **1 giây = 30 phút mô phỏng**, có dừng ở bước duyệt. Lượng khách và tốc độ đồng hồ là hai tham số khác nhau. 4× là giả định theo yêu cầu thử đông khách, chưa phải số đo AEON và chưa phải chạy thị trường private gốc. Không tự tăng sản lượng model để đảm bảo bán được mọi lượt mua.

Bấm nút **Model V6.06: baseline vs AI** trong thanh mô phỏng để xem bốn nhánh trên cùng luồng khách: BASELINE, M1_ONLY, M2_ONLY, JOINT_M1_M2. Phép so sánh này tự duyệt đề xuất hợp lệ, dùng cùng seed, cùng ngày và cùng luồng khách. Nó độc lập với quyết định quản lý đang thao tác trong ca. Chỉ so một ngày, không phải kết quả chính thức toàn kỳ.

Kết quả kiểm tra ngày 01/07/2022, seed 42: 799 lượt yêu cầu mua. Baseline bán 232, doanh thu 6.078.400đ; M2/Joint bán 244, doanh thu 6.394.000đ (+315.600đ, +5,19%). M1_ONLY bằng baseline. Cả bốn nhánh hết hàng; Joint không phục vụ được 555 lượt yêu cầu. Điều này cho thấy giới hạn nguồn cung/model khi tăng tải, không chứng minh model tối ưu hoặc uplift giá. Không có dữ liệu chi phí nên không tính lợi nhuận; tích hợp này chưa tính SHAP.

Các ngày test tiếp theo cần lịch sử ca trước đã đóng (prepared, sold, censor), không được thay khoảng thiếu bằng số bán tương lai. Thời tiết sau phần seed được giữ thiếu và impute bằng preprocessor đã fit; OOD dùng fallback đã khai báo. Để chạy chính thức trên thị trường private gốc, phải giữ quy trình FROZEN và tách quyền custodian/model; kết quả kịch bản 4× không được gộp với kết quả đó.
