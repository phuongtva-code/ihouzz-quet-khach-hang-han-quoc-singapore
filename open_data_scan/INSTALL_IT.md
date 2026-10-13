# Cài đặt và chạy hằng tuần: quét doanh nghiệp từ nguồn dữ liệu mở (dành cho IT)

Tài liệu này dành cho người chưa biết gì về dự án. Làm lần lượt từ trên xuống.

## 1. Mục đích

Mỗi tuần, máy chủ iHouzz tự thêm tối đa 60 dòng doanh nghiệp liên quan người Việt ở **Singapore** vào bảng "Dữ liệu AI quét" trên Lark Base (TGĐ xem trực tiếp trên Base, không cần báo cáo). Nguồn là bộ dữ liệu mở "Entities Registered with ACRA" trên data.gov.sg. Với **Hàn Quốc** và các nơi chưa có nguồn mở tự động, người vận hành bỏ file CSV lấy từ danh bạ công khai vào thư mục `inbox/`, script kiểm tra rồi nạp vào cùng bảng.

Chỉ lấy thông tin doanh nghiệp công khai, ghi nguồn và ngày quét, **chưa liên hệ khách**.

Bảng đích: Lark Base `PB76bICpAaGF5bsxubHl0WPygqd`, bảng "Dữ liệu AI quét" (`tbl9PvlYusTt1dlm`). Hai mã này đã nằm sẵn trong `scan_config.json`.

## 2. Ranh giới KHÔNG được vi phạm

- **Không dùng Google Maps / Google Places làm nguồn lưu vào Base.** Điều khoản Google Maps Platform (mục 3.2.3(a) "No Scraping" và 3.2.3(b) "No Caching") không cho lưu tên, địa chỉ doanh nghiệp từ Google ra ngoài dịch vụ, kể cả khi gọi API chính thức; Service Specific Terms mục 14.3 chỉ cho cache tạm vĩ độ/kinh độ tối đa 30 ngày, và place_id được cache. Đừng thêm Google Maps, Places API hay việc chép danh sách từ giao diện Maps vào script này. Nếu muốn dùng Google, cần văn bản xác nhận của pháp chế hoặc của Google trước. (Đã đọc trên trang điều khoản của Google ngày 13/10/2026; trang là bản lưu, hãy đối chiếu bản hiện hành.)
- **Không lấy người cá nhân.** Không đọc, không lưu tên cá nhân, link hồ sơ, danh sách thành viên nhóm, số điện thoại hay email cá nhân. Chỉ doanh nghiệp và tổ chức.
- **Không bỏ qua chặn của nguồn.** Nếu data.gov.sg hay mạng công ty trả 403 hoặc 429, script **dừng và báo** (mã thoát 2). Không đổi IP, không dùng proxy để né, không tăng tần suất.
- **Không bật nhóm hộ kinh doanh cá thể** (`include_sole_proprietorship` trong `scan_config.json`) khi chưa có đồng ý bằng văn bản của người phụ trách dự án và pháp chế. Nhóm này chiếm khoảng một nửa các kết quả khớp "viet" trong thử nghiệm, nhưng địa chỉ đăng ký của hộ cá thể có thể là nhà riêng của một người.
- **Giữ kín khóa.** Chỉ để trong `.env` (quyền 600). Không đưa lên git, không gửi qua chat hoặc email.
- **Không sửa hay xóa dòng cũ trong Base.** Script chỉ thêm dòng mới. Các cột "Quy mô", "Trạng thái duyệt", "Nhận xét TGĐ" luôn để trống cho TGĐ điền.

## 3. Cần chuẩn bị

| Việc | Biến trong `.env` | Bắt buộc |
|---|---|---|
| Ứng dụng Lark của công ty | `LARK_APP_ID`, `LARK_APP_SECRET` | Có |
| Lark quốc tế hay Feishu | `LARK_DOMAIN` (mặc định `https://open.larksuite.com`) | Không |
| Khóa data.gov.sg | `DATA_GOV_SG_API_KEY` | Không (có khóa thì giới hạn tốc độ cao hơn) |

Không cần khóa Google và không cần khóa Anthropic.

**Tạo ứng dụng Lark.** Các bước dưới đây là hướng dẫn chung, tên menu có thể khác tùy phiên bản Lark; hãy đối chiếu với tài liệu Lark Open Platform.

1. Vào Lark Developer Console (https://open.larksuite.com/app), đăng nhập bằng tài khoản quản trị của iHouzz, tạo "ứng dụng tùy chỉnh" (custom app), tên gợi ý `ihouzz-open-data-scan`.
2. Ở mục thông tin cơ bản, lấy **App ID** và **App Secret** điền vào `.env`.
3. Ở mục quyền (Permissions & Scopes), thêm quyền **xem và chỉnh sửa Base** (thường tên là `bitable:app`; nếu giao diện dùng tên mới thì chọn quyền đọc và quyền tạo bản ghi của Base).
4. Phát hành phiên bản ứng dụng và nhờ quản trị viên Lark duyệt nếu được yêu cầu.
5. **Thêm ứng dụng vào Base:** mở Base "Dữ liệu AI quét", trong menu `...` chọn thêm ứng dụng tài liệu (Add document app) và cấp quyền **chỉnh sửa**. Thiếu bước này thì Lark trả lỗi không có quyền dù ứng dụng đã có scope.

## 4. Cài đặt

Cần máy chủ Linux có **Python 3.10 trở lên**, ra được HTTPS tới `data.gov.sg` và `open.larksuite.com`.

```bash
# 1. Chép thư mục open_data_scan lên máy chủ, ví dụ /opt/ihouzz-open-data (chạy bằng user riêng, không dùng root)
cd /opt/ihouzz-open-data
python3 --version                 # phải từ 3.10 trở lên

# 2. Tạo file khóa
cp .env.example .env && chmod 600 .env
# mở .env và điền LARK_APP_ID, LARK_APP_SECRET

# 3. Quyền chạy
chmod +x run_weekly.sh sg_acra_scan.py import_directory.py
```

Không có thư viện nào cần cài thêm (chỉ dùng thư viện chuẩn của Python).

## 5. Chạy thử theo thứ tự

```bash
cd /opt/ihouzz-open-data

# a) Tự kiểm offline, không cần khóa, không cần mạng. Dòng cuối mỗi lệnh: "self-test: OK ..."
python3 sg_acra_scan.py --self-test
python3 import_directory.py --self-test
bash -n run_weekly.sh             # không in gì là cú pháp đúng

# b) Thử NGUỒN thật, không đụng Lark, không ghi gì. Cần ra được data.gov.sg.
#    Mong đợi: in vài dòng JSON và một dòng "Ứng viên hợp lệ ...".
set -a; . ./.env; set +a
python3 sg_acra_scan.py --no-base --max-new 5

# c) Thử ĐỌC Lark Base thật, vẫn không ghi gì
python3 sg_acra_scan.py --dry-run --max-new 5

# d) Chạy thật một lần nhỏ, rồi mở Base kiểm tra 5 dòng mới
python3 sg_acra_scan.py --max-new 5
```

**Lưu ý quan trọng:** người viết code đã kiểm định dạng phản hồi của API data.gov.sg (tên trường `uen`, `entity_name`, `uen_status_desc`, `entity_type_desc`, `uen_issue_date`, `reg_street_name`, `reg_postal_code`; phân trang bằng `offset`) qua trang công khai, nhưng **chưa chạy được script này trực tiếp tới data.gov.sg** vì môi trường phát triển chặn kết nối ra ngoài. Bước (b) là lần chạy thật đầu tiên. Nếu thất bại, đọc dòng lỗi trong `logs/` rồi báo lại; **đừng sửa code để né chặn**.

Ở bước (d), mở Base và kiểm các dòng mới: cột "Khu vực" là `Singapore`; "Ngày quét" đúng ngày chạy (12:00 giờ Việt Nam); "Nguồn dữ liệu" ghi ACRA; "Link nguồn" mở ra đúng bản ghi; "AI đánh giá" có A hoặc B; các cột TGĐ để trống.

## 6. Đặt lịch hằng tuần

Gợi ý: sáng thứ Hai, 07:59 giờ Việt Nam.

```bash
crontab -e
# Nếu máy chủ để múi giờ Asia/Ho_Chi_Minh:
59 7 * * 1  /bin/bash /opt/ihouzz-open-data/run_weekly.sh
# Nếu máy chủ để UTC (07:59 giờ Việt Nam = 00:59 UTC):
59 0 * * 1  /bin/bash /opt/ihouzz-open-data/run_weekly.sh
```

Nên đặt `MAILTO=` ở đầu crontab để nhận thư khi mã thoát khác 0. Nhật ký nằm trong `logs/` (mỗi tháng một file, thêm `run_weekly.log` và `last_exit_code.txt`).

## 7. Nạp danh bạ công khai bằng CSV (dùng cho Hàn Quốc)

Việc này do **người vận hành** làm, không phải IT. IT chỉ cần bảo đảm thư mục `inbox/` ghi được và `run_weekly.sh` chạy đều.

1. Lấy file mẫu `templates/mau_danh_ba.csv` (chỉ có dòng tiêu đề).
2. Từ danh bạ công khai (hội doanh nghiệp, hội đoàn Việt Nam tự công bố danh sách, website riêng của doanh nghiệp), điền mỗi doanh nghiệp một dòng.
3. Bỏ file vào `inbox/`. Lần chạy tuần sau (hoặc chạy tay `python3 import_directory.py`) sẽ kiểm tra và nạp. File đã xử lý chuyển sang `inbox/done/`; các dòng bị loại nằm trong file `.rejected.csv` kèm lý do.

Các cột:

| Cột | Bắt buộc | Ghi chú |
|---|---|---|
| `ten` | Có | Tên doanh nghiệp hoặc tổ chức đúng như trên trang nguồn |
| `khu_vuc` | Có | `Hàn Quốc`, `Singapore` hoặc `Quận Cam` |
| `nguon` | Có | Tên nguồn, ví dụ tên hội và loại danh bạ |
| `link_nguon` | Có | Đường link tới trang công khai chứa thông tin. Không nhận mạng xã hội, không nhận Google Maps (script tự loại) |
| `dia_chi`, `nganh` | Không | Không có `nganh` thì suy từ tên và ghi "(theo tên)" |
| `dien_thoai`, `website`, `email` | Không | Chỉ nhận khi `lien_he_do_doanh_nghiep_cong_bo` = `co`. Website phải là website riêng của doanh nghiệp. Email miễn phí (gmail, naver...) luôn bị bỏ |
| `lien_he_do_doanh_nghiep_cong_bo` | Có nếu có liên hệ | `co` nghĩa là chính doanh nghiệp hay tổ chức đã tự công bố liên hệ đó |
| `ngay_quet` | Không | `YYYY-MM-DD`; trống thì lấy ngày chạy |

Mỗi file tối đa 200 dòng. Dòng vi phạm luật bị loại tự động: không có link nguồn, link là Facebook/Zalo/LinkedIn/Instagram/TikTok, khu vực lạ, tên giống email hay số điện thoại, trùng với dòng đã có.

## 8. Mã thoát và cách xử lý

| Mã | Ý nghĩa | Việc cần làm |
|---|---|---|
| 0 | Ổn (có thể thêm 0 dòng nếu không còn gì mới) | Không |
| 1 | Thiếu cấu hình, `.env` sai quyền, hoặc tự kiểm thất bại | Đọc dòng lỗi trong `logs/`, sửa `.env` hoặc báo lại |
| 2 | Nguồn dữ liệu (data.gov.sg) hoặc mạng công ty chặn (403) hoặc giới hạn tốc độ (429) | **Dừng và báo lại.** Không né. Chờ rồi chạy tay lại vào hôm sau |
| 3 | Đã ghi một phần rồi lỗi (kể cả lỗi HTTP hay mất mạng giữa chừng) | Mở Base xem các dòng mới nhất; lần chạy sau tự bỏ qua dòng đã có (chống trùng) |
| 4 | Lark hoặc nguồn trả lỗi, chưa ghi gì. **403/429 từ Lark cũng vào đây** (lỗi quyền ứng dụng hoặc hạn mức, không phải "nguồn chặn") | Xem thông điệp lỗi trong log. Lỗi nói tên cột không tìm thấy: so tên cột trong `scan_config.json` (mục `columns`) với tên cột trong Base. Lỗi "Lark từ chối": kiểm bước 3.5 (app đã được thêm vào Base với quyền chỉnh sửa) |

## 9. Giới hạn đã biết

- **Không có điện thoại và website** cho dòng Singapore: bộ ACRA chỉ có tên, loại hình, tình trạng, đường và mã bưu chính. Muốn liên hệ cần bước khác (website riêng của doanh nghiệp, danh bạ hội đoàn, hoặc kênh có đồng ý).
- **Nhãn A/B của dòng ACRA có nghĩa khác nhãn của lô thử cũ.** Ở đây A = tên công ty có từ khóa Việt Nam rõ ràng (`vietnam`, `saigon`, `hanoi`...), B = chỉ có từ khóa yếu (`viet`, `pho`...). Không nói gì về liên hệ. Không có cách nào xác nhận chủ có phải người Việt hay không; cột "Lý do AI đánh giá" luôn ghi "chưa xác nhận chủ".
- **Cột "Ngành" chỉ là suy đoán từ tên** (ghi "theo tên"), hoặc "Chưa rõ ngành".
- **Hộ kinh doanh cá thể bị loại mặc định** (xem mục 2), nên nhiều quán ăn nhỏ chưa có trong dữ liệu.
- **ACRA cập nhật hằng tháng (ngày 16)**, nên các tuần giữa tháng thường không có dòng mới ngoài phần còn chờ. Script ghi tối đa 60 dòng mỗi lần, phần còn lại để tuần sau.
- **Hàn Quốc chưa có nguồn mở tự động.** Bước tiếp theo là IT chọn bộ dữ liệu mở của chính phủ Hàn trên data.go.kr (cần kiểm giấy phép và có khóa API); khi có bộ cụ thể, có thể viết thêm bộ nạp cho Hàn Quốc theo khuôn của `sg_acra_scan.py`. Cho tới lúc đó, Hàn Quốc đi qua CSV.
- **Ghi nguồn:** Singapore Open Data Licence v1.0 yêu cầu thông báo rõ nguồn khi dùng dữ liệu trong sản phẩm hoặc trang web, kèm đường link tới giấy phép (https://data.gov.sg/open-data-licence), và không được ngụ ý sự chứng thực của chính phủ. Cột "Nguồn dữ liệu" trong Base đã ghi nguồn; khi đưa dữ liệu ra ngoài công ty (báo cáo, sản phẩm), nhớ thêm thông báo này. Giấy phép không trao quyền đối với dữ liệu cá nhân.

## 10. Hàn Quốc: việc IT cần làm để có bộ nạp tự động

Người viết code **chưa đọc được** trang các bộ dữ liệu trên data.go.kr (trang từ chối công cụ đọc của họ), nên không biết chắc tên trường, tham số lọc và giấy phép của từng bộ. Họ cũng không đoán: đoán sai sẽ ra dữ liệu của một bộ khác mà trông vẫn như thật. Cần IT làm bốn việc rồi gửi kết quả lại để viết `kr_open_data_scan.py` theo khuôn của `sg_acra_scan.py`:

1. Trên https://www.data.go.kr, tìm bộ dữ liệu mở về cửa hàng hoặc doanh nghiệp có tên, địa chỉ và phân loại ngành. Một ứng viên cần kiểm là bộ thông tin cửa hàng (상가(상권)정보) của Cơ quan Xúc tiến Thị trường Doanh nghiệp nhỏ và vừa (소상공인시장진흥공단); đây chỉ là gợi ý chưa được kiểm.
2. Ghi lại **giấy phép** của bộ đó (thường là KOGL loại 1 đến 4 trên trang bộ dữ liệu). Chỉ dùng bộ cho phép lưu và dùng thương mại; nếu giấy phép có điều kiện ghi nguồn hay cấm thay đổi, ghi rõ để đưa vào cột "Nguồn dữ liệu".
3. Đăng ký sử dụng (활용신청), lấy khóa API, và ghi lại **hạn mức gọi mỗi ngày**.
4. Chạy tay một truy vấn mẫu cho một khu vực (ví dụ Ansan) và gửi lại: tên các trường trong phản hồi, tham số lọc theo khu vực và theo ngành, cách phân trang, và một vài dòng mẫu đã bỏ thông tin cá nhân (nếu có). Không gửi khóa API qua chat hay email.

Trong lúc chờ, Hàn Quốc đi qua file CSV (mục 7). Dữ liệu cửa hàng thường không có chỉ dấu "người Việt" nào ngoài tên, nên bộ nạp Hàn Quốc sẽ lọc theo từ khóa trong tên (ví dụ 베트남, 쌀국수, tên Việt viết bằng chữ Latinh) và gắn nhãn tương tự dòng Singapore.
