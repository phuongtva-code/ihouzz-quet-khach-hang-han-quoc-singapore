# Quét khách hàng AI cho iHouzz

Gói mã nguồn của AI Team gồm ba phần: giao diện công cụ quét (HTML/CSS/JS), bộ script quét doanh nghiệp từ dữ liệu mở vào Lark Base, và bộ script thu tín hiệu cộng đồng người Việt tại Hàn.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `web/` | Giao diện công cụ, bản V19: `index.html`, `assets/styles.css`, `assets/ui.js`, `assets/data.js`. Chạy tĩnh, không cần build |
| `open_data_scan/` | Việc 1 của TGĐ: doanh nghiệp người Việt ở Singapore (ACRA, data.gov.sg) và Hàn Quốc (CSV danh bạ công khai) vào bảng "Dữ liệu AI quét" trên Lark Base. Xem `INSTALL_IT.md` trong thư mục |
| `reddit_scan/` | Tín hiệu nhu cầu ẩn danh từ Reddit và thống kê KOSIS, xuất file `.jsonl` để nạp vào giao diện. Xem `INSTALL_IT.md` trong thư mục |
| `.github/workflows/ci.yml` | Kiểm tra cú pháp và tự kiểm các script, đăng `web/` lên GitHub Pages |

## Xem giao diện trên máy

```bash
python3 -m http.server 8080 --directory web
# mở http://localhost:8080
```

Giao diện dùng font Geist từ Google Fonts, nên cần có Internet để hiện đúng chữ.

## Đăng lên GitHub Pages

1. Đưa toàn bộ thư mục này lên một repo GitHub, nhánh mặc định `main`.
2. Vào **Settings → Pages**, mục **Build and deployment → Source**, chọn **GitHub Actions**. Workflow có sẵn ở `.github/workflows/ci.yml` (job `pages`) sẽ tự đăng thư mục `web/` mỗi khi push vào `main`. Link nằm ở **Settings → Pages** sau lần chạy đầu tiên.
3. Repo nên để **Private** vì trang có các màn nội bộ (bản đồ cộng đồng, bảng liên hệ). Lưu ý: GitHub Pages cho repo private chỉ dùng được với gói trả phí (Pro/Team/Enterprise) — nếu tài khoản đang ở gói Free, bỏ qua bước deploy Pages và chỉ chạy công cụ bằng cách tải code về mở local (xem mục trên), hoặc chuyển repo sang Public khi cần demo (dữ liệu hiển thị vẫn chỉ là dữ liệu mẫu, xem mục dưới).
4. Workflow này chưa được chạy thử trên GitHub Actions thật. Nếu job báo lỗi, gửi lại thông báo lỗi để chỉnh.

## Giao diện chạy ngoài Claude thì khác gì

Bản V19 gốc chạy trên claude.ai và dùng ba khả năng của nền tảng đó: kho dữ liệu trong trang (nguồn, thống kê, tổ chức, tín hiệu), "Máy xếp nhóm" do Claude phân loại bài, và nhận diện người xem để phân quyền. Trên GitLab Pages những khả năng này không có, nên:

- Trang tự rơi về **chế độ ví dụ**: hiện đủ 8 màn hình với dữ liệu mẫu, có nhãn "Ví dụ · chưa có số thật".
- "Thêm nguồn" chỉ thêm dòng thử vào bảng và báo rõ là bản thử, tải lại trang là mất.
- "Nạp dữ liệu" và "Nhận file từ máy chủ" (Màn 05) cần kho dữ liệu nên không dùng được.
- Muốn số thật trên GitLab cần thêm một máy chủ lưu trữ (ví dụ Lark Base qua API). Phần này chưa làm.

Mã giao diện giống hệt bản V19 trên claude.ai, chỉ tách từ một file thành bốn file. Bộ kiểm tự động (Playwright, 57 điểm kiểm) cho kết quả giống nhau trước và sau khi tách.

## Script cho IT

- Khóa và mật khẩu để trong file `.env` (quyền 600) trên máy chủ, **không đưa lên git**. `.gitignore` đã chặn `.env`; chỉ có `.env.example` là mẫu.
- `open_data_scan` chỉ dùng thư viện chuẩn của Python 3.10 trở lên. `reddit_scan` cần các gói trong `requirements.txt` khi chạy thật. Phần tự kiểm của cả hai chạy offline, chỉ cần thư viện chuẩn:

```bash
cd open_data_scan && python3 sg_acra_scan.py --self-test && python3 import_directory.py --self-test
cd ../reddit_scan && python3 reddit_ingest.py --self-test && python3 export_for_page.py --self-test && python3 kosis_ingest.py --self-test
```

- `open_data_scan` chưa chạy thật tới data.gov.sg và Lark Base (môi trường phát triển bị chặn kết nối). Lần chạy thật đầu tiên do IT làm theo `open_data_scan/INSTALL_IT.md`, mục 5.
- Hàn Quốc chưa có script tự chạy: dữ liệu mở data.go.kr cần IT kiểm tra bộ dữ liệu và giấy phép. Trước mắt đi qua file CSV danh bạ công khai.
- `reddit_scan/kosis_config.json` để trống mã bảng KOSIS, chờ IT điền.

## Ranh giới dữ liệu (giữ nguyên ở mọi thay đổi)

- Không viết công cụ lấy danh sách thành viên hay link trang cá nhân của nhóm Facebook, và không thu dữ liệu định danh cá nhân khi chưa có đồng ý. Căn cứ: Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15, PIPA Hàn Quốc, điều khoản Meta.
- Liên hệ cá nhân chỉ qua kênh người dùng tự đồng ý (biểu mẫu). Nhóm cộng đồng chỉ lấy tín hiệu ẩn danh ở mức nhóm.
- Dữ liệu doanh nghiệp: chỉ thông tin công khai, ghi rõ nguồn và ngày quét. Không lưu tên, địa chỉ lấy từ Google Maps vào cơ sở dữ liệu riêng (điều khoản Google Maps Platform mục 3.2.3).
- Nếu một trang hay API chặn truy cập (403, 429, robots), dừng lại và báo, không dùng cách vòng.
