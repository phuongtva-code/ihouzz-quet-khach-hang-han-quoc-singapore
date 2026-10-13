# Reddit ingest — tín hiệu nhu cầu (lớp 3)

Script lấy thảo luận **công khai** trên Reddit liên quan đến cộng đồng người Việt
tại Hàn Quốc, ẩn danh rồi phân loại thành tín hiệu nhu cầu cho dự án
"Quét cộng đồng người Việt tại Hàn".

Đây là **lớp 3** trong mô hình quét: đo *cộng đồng đang bàn gì* (xu hướng, chủ đề,
sắc thái), **không** tạo đầu mối cá nhân, **không** lưu tên/username/link/ảnh.

## Ranh giới đã giữ trong code
- Chỉ đọc qua **API chính thức** của Reddit (OAuth script app), nội dung công khai.
- Không bao giờ đọc hay lưu tác giả bài viết.
- Ẩn danh trước khi phân loại: bỏ email, số điện thoại, URL, `u/handle`.
- Chỉ lưu: subreddit, ngày, nhãn phân loại, và trích đoạn **≤ 200 ký tự đã ẩn danh**.
- Tự loại bài quảng cáo/rao bán khỏi thống kê nhu cầu.

## Cài đặt
```bash
pip install -r requirements.txt
```

## Chạy thử ngay (không cần khóa)
```bash
python3 reddit_ingest.py --self-test
```
Kiểm tra phần ẩn danh + phân loại tạm, chạy hoàn toàn offline.

## Chạy thật
1. Tạo "script app" tại https://www.reddit.com/prefs/apps → lấy client id & secret.
2. Đặt biến môi trường:
```bash
export REDDIT_CLIENT_ID=xxx
export REDDIT_CLIENT_SECRET=xxx
export REDDIT_USER_AGENT="ihouzz-scan/0.1 by u/<tài_khoản_reddit>"

# Để AI phân loại bằng Claude (thiếu thì script dùng nhãn tạm bằng luật):
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_MODEL=claude-sonnet-4-5          # đổi theo model đang dùng
```
3. Chạy:
```bash
python3 reddit_ingest.py --days 7 --limit 60 --out out/reddit_signals.jsonl
```
Kết quả nằm ở `out/reddit_signals.jsonl` (mỗi dòng 1 tín hiệu). File
`out/seen_hashes.txt` giúp lần chạy sau không lặp bài cũ.

## Đẩy sang Lark Base (tùy chọn)
Khi đã có bảng "Tín hiệu nhu cầu" trong Lark Base, đặt thêm:
```bash
export LARK_APP_ID=cli_xxx
export LARK_APP_SECRET=xxx
export LARK_BASE_APP_TOKEN=xxx     # app_token của Base
export LARK_TABLE_ID=tblxxx
# export LARK_DOMAIN=https://open.larksuite.com   # mặc định (bản quốc tế)
```
Bỏ cờ `--no-lark` để script tự đẩy. Cần sửa tên cột trong hàm `push_to_lark`
cho khớp đúng bảng của mình.

## Tham số
| Cờ | Mặc định | Ý nghĩa |
|---|---|---|
| `--days` | 7 | lấy bài trong N ngày gần nhất |
| `--limit` | 50 | số bài tối đa mỗi từ khóa |
| `--out` | out/reddit_signals.jsonl | file kết quả |
| `--seen` | out/seen_hashes.txt | file khử trùng lặp |
| `--no-lark` | tắt | chỉ ghi file, không đẩy Lark |
| `--self-test` | — | chạy thử offline |

## Lưu ý thực tế
Cộng đồng người Việt tại Hàn chủ yếu sinh hoạt ở Facebook/Zalo, nên **lượng
tín hiệu trên Reddit sẽ mỏng**. Reddit dùng để dựng và kiểm chứng pipeline
(API → ẩn danh → Claude phân loại → Lark). Cùng pipeline này có thể cắm thêm
nguồn khác về sau. Chỉnh `SUBREDDITS` và `KEYWORDS` ở đầu file để mở rộng.
