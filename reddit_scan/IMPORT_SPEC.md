# Định dạng file nạp vào trang ("Cửa nhận file")

Script chạy trên máy chủ iHouzz xuất ra **JSONL** (mỗi dòng 1 đối tượng JSON, UTF-8).
Người vận hành mở trang → Màn 05 → "Nhận file từ máy chủ" → chọn file. Trang kiểm tra
từng dòng, loại dòng sai, rồi lưu vào kho. Nạp lại cùng một file không bị trùng
(trang dùng `id` tính từ nội dung để khử trùng).

## Quy tắc bất biến (trang sẽ TỪ CHỐI dòng vi phạm)
- Không có khóa nào tên: `author`, `username`, `user`, `profile`, `member`, `members`,
  `friend`, `email_nguoi_dang`, `link_nguoi_dang`, `permalink_nguoi_dang`.
- `trich_doan` ≤ 200 ký tự, đã bỏ email / số điện thoại / URL / `u/handle`.
- `la_quang_cao = true` → dòng bị bỏ (không đếm vào nhu cầu).
- Chỉ nhận 3 loại: `signal`, `stat`, `org`. Không có loại "cá nhân".

## 1) `kind = "signal"` — tín hiệu nhu cầu (nhóm ③), ẩn danh
Khớp đúng đầu ra của `reddit_ingest.py` (thêm `kind`). Nếu dòng không có `kind`
nhưng có `chu_de` thì trang coi là `signal`.

```json
{"kind":"signal","source":"reddit","subreddit":"korea","ngay_dang":"2026-10-12",
 "tuan":"2026-W42","matched_keyword":"gửi tiền về",
 "chu_de":"Tài chính và gửi tiền","nhu_cau_ro":"Chỉ bàn luận","muc_cu_the":"Hỏi chung",
 "dia_phuong_vn":"","noi_o_tai_han":"Ansan","nhom_nguoi":"Lao động",
 "ngon_ngu":"Tiếng Việt","sac_thai":"Trung tính","la_quang_cao":false,
 "trich_doan":"Hỏi cách gửi tiền về Việt Nam ít phí…"}
```

Giá trị cho phép:
- `chu_de`: Tài chính và gửi tiền | Nhà đất tại VN | Việc làm và visa | Đời sống tại Hàn | Học tập | Về nước, định cư | Gia đình | Khác
- `nhu_cau_ro`: Có | Không | Chỉ bàn luận
- `muc_cu_the`: Hỏi chung | Có ngân sách | Có địa điểm | Có thời điểm
- `nhom_nguoi`: Lao động | Du học | Kết hôn, định cư | Chuyên gia | Chủ doanh nghiệp | Không rõ
- `ngon_ngu`: Tiếng Việt | Lẫn tiếng Hàn | Khác
- `sac_thai`: Tích cực | Trung tính | Lo lắng, bức xúc

## 2) `kind = "stat"` — số thống kê chính thức (nhóm ②)
Một dòng = một tỉnh/thành, một kỳ.

```json
{"kind":"stat","metric":"nguoi_viet_theo_tinh","area":"Gyeonggi","period":"2026-09",
 "value":123456,"female":71000,"src":"KOSIS · <tên bảng> · <link>","confidence":"chính thức"}
```
- `area`: Toàn quốc | Seoul | Busan | Incheon | Daegu | Daejeon | Gwangju | Ulsan | Sejong | Gyeonggi | Gangwon | Chungcheong Bắc | Chungcheong Nam | Jeolla Bắc | Jeolla Nam | Gyeongsang Bắc | Gyeongsang Nam | Jeju
- `period`: `YYYY` hoặc `YYYY-MM`
- `value`: số người Việt (số nguyên ≥ 0). `female` tùy chọn.
- `confidence`: `chính thức` (do cơ quan nhà nước công bố, kèm link) | `thứ cấp` (trích lại qua bên thứ ba)
- `src`: bắt buộc, ghi rõ tên bảng + link.

Tên tỉnh Hàn → `area`:
서울특별시→Seoul · 부산광역시→Busan · 인천광역시→Incheon · 대구광역시→Daegu · 대전광역시→Daejeon ·
광주광역시→Gwangju · 울산광역시→Ulsan · 세종특별자치시→Sejong · 경기도→Gyeonggi · 강원(특별자치)도→Gangwon ·
충청북도→Chungcheong Bắc · 충청남도→Chungcheong Nam · 전북(특별자치)도/전라북도→Jeolla Bắc · 전라남도→Jeolla Nam ·
경상북도→Gyeongsang Bắc · 경상남도→Gyeongsang Nam · 제주특별자치도→Jeju

## 3) `kind = "org"` — đầu mối của TỔ CHỨC (nhóm ①), chỉ liên hệ chung công khai
```json
{"kind":"org","name":"Trung tâm hỗ trợ gia đình đa văn hóa Ansan","type":"Hội đoàn",
 "province":"Gyeonggi","subarea":"Ansan","phone":"","email":"","web":"","fb":"","zalo":"",
 "yt":"","addr":"","src":"https://… (trang chính thức của tổ chức)"}
```
- `type`: Hội đoàn | Doanh nghiệp Việt tại Hàn | Tổ chức phía Việt Nam | Nhóm, kênh
- `src` bắt buộc (trang chính thức nơi tổ chức tự công bố liên hệ).
- Chỉ liên hệ CHUNG của tổ chức (tổng đài, email chung, website, trang tổ chức). Không số cá nhân.
