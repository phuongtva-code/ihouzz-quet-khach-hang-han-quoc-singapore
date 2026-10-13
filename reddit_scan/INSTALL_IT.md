# Cài đặt và chạy hằng ngày — dành cho IT

Tài liệu này dành cho người chưa biết gì về dự án. Làm lần lượt từ trên xuống.

## 1. Mục đích

Mỗi ngày, hệ thống lấy các bài thảo luận **công khai** trên Reddit về cộng đồng người Việt ở Hàn Quốc (đã ẩn danh, chỉ giữ nhãn phân loại và một trích đoạn ngắn) cùng số người Việt theo tỉnh/thành do cơ quan thống kê Hàn Quốc (KOSIS) công bố. Kết quả gom thành **một file** `out/import_YYYYMMDD.jsonl`; người vận hành nạp file đó vào trang web nội bộ (Màn 05, "Nhận file từ máy chủ"). IT chỉ cần cài, đặt lịch và bảo đảm file ra đều đặn.

## 2. Ranh giới KHÔNG được vi phạm

- **Không lấy thành viên hay trang cá nhân.** Không đọc, không lưu tên người đăng, username, ảnh đại diện, link hồ sơ, danh sách thành viên hay bạn bè. Code cố ý không đọc tác giả bài viết; đừng sửa để lấy thêm.
- **Không bỏ qua chặn của website.** Nếu Reddit, KOSIS hay trang nào từ chối hoặc chặn máy chủ (lỗi 403, 429, captcha, báo vượt giới hạn), hãy **dừng và báo lại**. Không đổi IP, không dùng proxy để né, không giả User-Agent, không dùng tài khoản không phải của công ty.
- **Chỉ dùng API chính thức.** Reddit qua ứng dụng (OAuth) do iHouzz đăng ký; KOSIS qua OpenAPI với khóa của iHouzz. Không cào trang web, không dùng nguồn không chính thức.
- **Giữ nguyên bước ẩn danh.** Không tắt hay nới bước ẩn danh trong `reddit_ingest.py` và `export_for_page.py`; không cho trích đoạn dài quá 200 ký tự.
- **Giữ kín khóa API.** Chỉ để trong file `.env` (quyền 600). Không gửi qua chat/email, không đưa lên git.
- **Không tăng tần suất gọi** hay bỏ các khoảng nghỉ có sẵn trong code.

## 3. Các khóa cần xin

| Nguồn | Tên biến môi trường | Bắt buộc | Cách xin |
|---|---|---|---|
| Reddit | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` | Có | Xem bên dưới |
| Anthropic (AI phân loại) | `ANTHROPIC_API_KEY` | Có | Xem bên dưới |
| Anthropic | `ANTHROPIC_MODEL` | Không | Để trống thì dùng tên model mặc định trong code (`claude-sonnet-4-5`). Chỉ đặt nếu model đó không còn dùng được |
| KOSIS (thống kê Hàn Quốc) | `KOSIS_API_KEY` | Không (thiếu thì bỏ qua KOSIS) | Xem bên dưới |

**Reddit.** Dùng tài khoản Reddit của công ty (không dùng tài khoản cá nhân của nhân viên). Vào https://www.reddit.com/prefs/apps, bấm "create another app", đặt tên `ihouzz-scan`, chọn loại **script**, ô "redirect uri" điền `http://localhost:8080` (bắt buộc điền nhưng không dùng tới). Sau khi tạo: `REDDIT_CLIENT_ID` là dòng chữ ngắn ngay dưới tên app, `REDDIT_CLIENT_SECRET` là ô "secret". `REDDIT_USER_AGENT` đặt đúng mẫu: `ihouzz-scan/0.1 by u/<tên_tài_khoản_reddit_công_ty>`. Lưu ý: chính sách của Reddit về cấp quyền API có thể đòi đăng ký hoặc chờ duyệt trước khi dùng. Nếu gặp yêu cầu đó, làm đúng theo hướng dẫn của Reddit và chờ; không dùng đường khác.

**Anthropic.** Đăng nhập https://console.anthropic.com bằng tài khoản tổ chức của iHouzz, vào mục API Keys, tạo khóa mới, đặt tên `ihouzz-scan`. Nạp tiền hoặc bật thanh toán, và đặt hạn mức chi tiêu hằng tháng. Mỗi bài chỉ một lần gọi ngắn nên chi phí nhỏ. Thiếu khóa này thì `run_daily.sh` **từ chối chạy** (xem mục 9 vì sao).

**KOSIS.** Vào https://kosis.kr/openapi, đăng nhập (đăng ký thành viên nếu chưa có), chọn mục đăng ký sử dụng OpenAPI (`OpenAPI 활용신청`). Sau khi được cấp, lấy chuỗi "인증키" (khóa xác thực) trong trang quản lý. Giao diện chủ yếu bằng tiếng Hàn và tên menu có thể thay đổi; hãy tìm mục có chữ `OpenAPI` và `인증키`.

## 4. Cài đặt

Cần máy chủ Linux có **Python 3.10 trở lên**, ra được internet (HTTPS) tới reddit.com, api.anthropic.com và kosis.kr.

```bash
# 1. Chép thư mục reddit_scan lên máy chủ, ví dụ /opt/ihouzz-scan (nên chạy bằng một user riêng, không dùng root)
cd /opt/ihouzz-scan
python3 --version                      # phải từ 3.10 trở lên

# 2. Cài thư viện (venv để không lẫn với hệ thống; run_daily.sh tự dùng .venv nếu có)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Tạo file khóa
cp /dev/null .env && chmod 600 .env
```

Mở `.env` và điền (mỗi dòng một biến, giá trị đặt trong dấu nháy kép):

```bash
export REDDIT_CLIENT_ID="..."
export REDDIT_CLIENT_SECRET="..."
export REDDIT_USER_AGENT="ihouzz-scan/0.1 by u/ten_tai_khoan_cong_ty"
export ANTHROPIC_API_KEY="sk-ant-..."
export KOSIS_API_KEY="..."            # có thể điền sau
```

## 5. Chạy thử (không cần khóa, không cần mạng)

```bash
cd /opt/ihouzz-scan
.venv/bin/python reddit_ingest.py --self-test      # dòng cuối: "self-test: OK ..."
.venv/bin/python export_for_page.py --self-test    # dòng cuối: "self-test: OK ..."
.venv/bin/python kosis_ingest.py --self-test       # dòng cuối: "self-test: OK ..."
bash -n run_daily.sh                               # không in gì là cú pháp đúng
```

Ba lệnh đầu chỉ kiểm tra logic bằng dữ liệu mẫu. Riêng `kosis_ingest.py --self-test` dùng dữ liệu **giả lập** (không phải số thật), nên "OK" ở đó chưa chứng minh mã bảng của bạn đúng; việc đó kiểm ở mục 6.

## 6. Điền mã bảng KOSIS

Mã bảng KOSIS trong `kosis_config.json` (`orgId`, `tblId`, `itmId`, `objL1`…, `prdSe`) **đang để trống có chủ đích**. Người viết code không biết chắc mã của bảng "người nước ngoài theo quốc tịch × tỉnh" nên không đoán: mã sai sẽ ra số của một bảng khác mà trông vẫn như thật. Khi còn trống, KOSIS tự bị bỏ qua và phần Reddit vẫn chạy bình thường. Cách điền:

1. Vào https://kosis.kr, tìm thống kê, gõ `외국인 국적 시도` (hoặc `국적별 외국인 시도`).
2. Chọn bảng có đủ hai chiều: **tỉnh/thành (시도)** và **quốc tịch (국적)**; có thêm **giới tính (성별)** thì lấy được cột nữ. Nếu có nhiều bảng phù hợp, các bảng đếm khác nhau (người nước ngoài đăng ký, cư dân nước ngoài, người lưu trú...), nên hãy hỏi người phụ trách dự án chọn bảng nào, đừng tự quyết.
3. Trong bảng, chọn `베트남` (Việt Nam), các tỉnh/thành và kỳ cần lấy, rồi dùng chức năng tạo URL OpenAPI của KOSIS (`URL 생성`, thường nằm ở nút OpenAPI trên trang bảng). KOSIS sẽ hiện một đường dẫn có dạng `...getList&apiKey=...&itmId=...&objL1=...&objL2=...&prdSe=...&orgId=...&tblId=...`.
4. Chép từng giá trị đó vào `kosis_config.json`: `orgId`, `tblId`, `itmId`, `objL1`…`objL8` (chiều nào không có thì để trống), `prdSe` (`Y` = theo năm, `M` = theo tháng). **Không** chép `apiKey` vào file này.
   Cách khác để tìm mã: `OpenAPI 활용신청` → mục danh mục thống kê (`통계목록`), duyệt theo cơ quan để lấy `orgId`, `tblId`.
5. Điền `ten_bang` (tên bảng như hiển thị trên KOSIS) để ghi vào nguồn của từng dòng.
6. Thử bằng lệnh sau, lệnh này gọi KOSIS thật, in vài dòng đầu và **không ghi file**:

```bash
set -a; . ./.env; set +a
.venv/bin/python kosis_ingest.py --dry-run
```

7. **Đối chiếu 2–3 con số** (ví dụ Việt Nam ở Seoul và Gyeonggi, đúng kỳ) với trang bảng trên kosis.kr. Chỉ khi khớp mới đưa vào chạy hằng ngày. Lần đầu muốn nạp bù nhiều kỳ: thêm `--so-ky 12`.

Script tự dừng và nói rõ nếu: không xác định được chiều nào là tỉnh/quốc tịch/giới tính (điền `truc_tinh`, `truc_quoc_tich`, `truc_gioi_tinh` trong config), có số liệu bị trùng (chiều thừa chưa chốt về mục "Tổng"), không thấy mục Việt Nam, hoặc đơn vị không phải "người". Phần mô tả giao diện KOSIS ở trên theo hiểu biết của người viết, chưa kiểm chứng; nếu menu khác, làm theo giao diện thực tế.

## 7. Chạy thật một lần, rồi đặt lịch

```bash
cd /opt/ihouzz-scan
bash run_daily.sh; echo "mã thoát: $?"
cat out/log_$(TZ=Asia/Seoul date +%Y%m%d).txt
```

Đọc log: cần thấy `KẾT QUẢ: out/import_YYYYMMDD.jsonl có N dòng` và `THÀNH CÔNG`. Lần chạy thật đầu tiên cũng là lần kiểm chứng việc gọi Reddit và KOSIS (phần đó chưa được thử ở môi trường phát triển vì bị chặn mạng). Có lỗi thì xem mục 10.

**Đặt lịch 03:00 hằng ngày theo giờ Hàn Quốc (KST, UTC+9).** Cron chạy theo múi giờ của máy chủ, nên phải chọn đúng một trong hai dòng sau. Xem múi giờ máy chủ bằng `timedatectl | grep "Time zone"`. Sửa bằng `crontab -e`:

```cron
# Máy chủ đang để giờ Hàn Quốc (Asia/Seoul): 03:00 KST
0 3 * * * /bin/bash /opt/ihouzz-scan/run_daily.sh

# Máy chủ để giờ UTC (thường gặp trên cloud): 03:00 KST = 18:00 UTC của ngày hôm trước
0 18 * * * /bin/bash /opt/ihouzz-scan/run_daily.sh
```

Chỉ dùng **một** dòng. Hàn Quốc không có giờ mùa hè nên quy đổi này không đổi quanh năm. Tên file log và file import luôn lấy ngày theo giờ Hàn Quốc, bất kể máy chủ để múi giờ nào. Muốn nhận thư khi có lỗi, thêm dòng `MAILTO=địa_chỉ_email_của_IT` ở đầu crontab: script chỉ in ra màn hình khi có lỗi.

Các file trong `out/`:

| File | Ý nghĩa |
|---|---|
| `import_YYYYMMDD.jsonl` | **File đưa cho người vận hành.** Chạy lại trong cùng ngày thì giữ dòng cũ, chỉ thêm dòng mới |
| `log_YYYYMMDD.txt` | Nhật ký ngày đó |
| `reddit_signals.jsonl`, `kosis_stats.jsonl` | Kết quả trung gian của từng bước |
| `seen_hashes.txt` | Ghi nhớ bài đã xử lý. **Không xóa** (xóa thì bài cũ bị xử lý lại, tốn tiền AI; trang vẫn tự loại trùng) |

## 8. Kiểm tra file trước khi đưa người vận hành

```bash
cd /opt/ihouzz-scan
F=out/import_$(TZ=Asia/Seoul date +%Y%m%d).jsonl
.venv/bin/python export_for_page.py --kiem-tra "$F"     # phải in "giữ N, bỏ 0"
wc -l "$F"                                              # số dòng
grep -ciE '"(author|username|user|profile|member|members|friend)"' "$F"   # phải ra 0
grep '"kind": "signal"' "$F" | grep -cE '@|https?://|u/'                  # phải ra 0
head -n 3 "$F"                                          # nhìn bằng mắt vài dòng
```

Nếu hai lệnh `grep` ra số khác 0, hoặc `--kiem-tra` báo "bỏ" khác 0: **đừng giao file**, báo lại cho người phát triển. File 0 dòng không phải lỗi (tuần vắng bài), nhưng nhiều ngày liền 0 dòng thì xem log. Giao file qua kênh nội bộ của công ty. Người vận hành mở trang, Màn 05, "Nhận file từ máy chủ", chọn file; nạp lại cùng file nhiều lần không bị trùng.

## 9. Vài điều nên biết về cách chạy

- `run_daily.sh` thiếu `ANTHROPIC_API_KEY` sẽ **từ chối chạy**. Lý do: không có AI thì script gắn nhãn tạm cho mọi bài và đánh dấu bài đã xử lý, nên bài đó mất vĩnh viễn mà chưa được phân loại thật.
- Dòng mang nhãn tạm (do AI lỗi từng bài) bị loại khỏi file import. Log sẽ có dòng "CẢNH BÁO: n bài phân loại AI lỗi".
- Mặc định không đẩy sang Lark Base (luồng chính là file import). Muốn đẩy như mô tả trong `README.md`, đặt `PUSH_LARK=1` trong `.env` cùng các biến `LARK_*`.
- Bước KOSIS chưa cấu hình thì log ghi "BỎ QUA KOSIS" và mọi thứ vẫn xong (mã thoát 0). KOSIS lỗi thật thì log ghi "CẢNH BÁO", script vẫn xuất file (không có số KOSIS lần đó) và thoát mã 0.

## 10. Nếu lỗi

Mã thoát của `run_daily.sh`: **0** xong, **1** thiếu biến bắt buộc hoặc đang có lượt chạy khác, **2** bước Reddit hỏng, **3** bước xuất file hỏng. Chi tiết luôn nằm trong `out/log_YYYYMMDD.txt`.

| Dấu hiệu | Làm gì |
|---|---|
| Mã 1, "thiếu biến môi trường bắt buộc" | Bổ sung đúng biến đó vào `.env` |
| Mã 1, "đang có lượt chạy khác" | Chờ lượt kia xong; nếu treo nhiều giờ, kiểm tra tiến trình `run_daily.sh` |
| Mã 2, "Reddit không trả về bài nào và có lỗi khi tìm" | Kiểm tra 3 biến `REDDIT_*`, app đã được Reddit duyệt chưa, máy chủ ra được internet chưa. Nếu log có 403, 429 hoặc dấu hiệu bị chặn: **dừng, báo lại, không né** |
| Mã 3, xuất file lỗi | Đọc lý do trong log. Bài của lượt đó được giữ ở `out/reddit_signals_YYYYMMDD_chua_xuat.jsonl`; sửa xong chạy `export_for_page.py --in <file đó>` |
| "BỎ QUA KOSIS" | Bình thường nếu chưa điền mã bảng. Làm mục 6 khi sẵn sàng |
| "CẢNH BÁO: KOSIS lỗi" | Đọc dòng `LỖI KOSIS:` trong log (thường là khóa sai/hết hạn hoặc mã trong config sai) |
| File import ít dòng, log có "bỏ N dòng" | Mỗi dòng bị bỏ đều có lý do ghi trong log; dòng bị bỏ là bình thường nếu là quảng cáo hoặc nhãn lạ |
| Không có log mới | Cron không chạy: kiểm tra `crontab -l`, đường dẫn tuyệt đối, và log hệ thống của cron |
| Lỗi lạ chưa gặp | Gửi người phát triển file `out/log_YYYYMMDD.txt` (log không chứa khóa API) |
