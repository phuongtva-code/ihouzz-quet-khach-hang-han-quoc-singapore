#!/usr/bin/env bash
# run_daily.sh — Chạy trọn chuỗi thu thập hằng ngày cho dự án "Quét cộng đồng người Việt tại Hàn":
#   1) reddit_ingest.py --days 7        BẮT BUỘC  (tín hiệu nhu cầu từ Reddit, đã ẩn danh)
#   2) kosis_ingest.py                  TÙY CHỌN  (số người Việt theo tỉnh từ KOSIS; chưa cấu hình thì bỏ qua)
#   3) export_for_page.py               BẮT BUỘC  (gom + kiểm tra -> out/import_YYYYMMDD.jsonl)
# Log: out/log_YYYYMMDD.txt (ngày theo giờ Hàn Quốc). Không in khóa API ra log.
#
# Mã thoát:  0 = xong (file import đã ghi; có thể kèm cảnh báo KOSIS trong log)
#            1 = thiếu biến môi trường bắt buộc, hoặc đang có lượt chạy khác
#            2 = bước Reddit hỏng      3 = bước xuất file import hỏng
#            4 = Reddit CHẶN (403/429): đã dừng ngay theo ranh giới dữ liệu, không né; báo IT, chạy lại sau
#
# Khóa API đọc từ file .env cạnh script (hoặc file ở biến IHOUZZ_ENV_FILE), vì cron không có
# biến môi trường của người dùng. Biến PYTHON (tùy chọn) chỉ định trình Python; nếu có thư mục
# .venv cạnh script thì dùng nó. Biến PUSH_LARK=1 (tùy chọn) cho reddit_ingest.py đẩy thêm sang
# Lark Base như trong README.md; mặc định KHÔNG đẩy, vì luồng chính là file import.

set -u
set -o pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 1
cd "$DIR" || exit 1

ENV_FILE="${IHOUZZ_ENV_FILE:-$DIR/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

if [ -n "${PYTHON:-}" ]; then
  PY="$PYTHON"
elif [ -x "$DIR/.venv/bin/python" ]; then
  PY="$DIR/.venv/bin/python"
else
  PY="python3"
fi

# Ngày theo GIỜ HÀN QUỐC (cron 03:00 KST là 18:00 UTC hôm trước, không được lấy ngày UTC).
kst_day() {
  if [ "$(TZ=Asia/Seoul date +%z 2>/dev/null)" = "+0900" ]; then
    TZ=Asia/Seoul date +%Y%m%d
  else
    date -u -d '+9 hours' +%Y%m%d   # máy không có dữ liệu múi giờ: tự cộng 9 tiếng (GNU date)
  fi
}
DAY="${RUN_DAY:-$(kst_day)}"

mkdir -p out || exit 1
LOG="out/log_${DAY}.txt"
SIGNALS="out/reddit_signals.jsonl"
STATS="out/kosis_stats.jsonl"
IMPORT="out/import_${DAY}.jsonl"

log() { printf '[%s] %s\n' "$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z')" "$*" >> "$LOG"; }

fail() {  # fail <mã thoát> <thông báo>
  log "LỖI: $2"
  log "=== KẾT THÚC run_daily.sh: THẤT BẠI (mã $1) ==="
  echo "run_daily.sh LỖI: $2 (chi tiết: $DIR/$LOG)" >&2
  exit "$1"
}

# Chạy một bước, ghi toàn bộ đầu ra vào log, giữ bản sao ở $LAST_OUT để kiểm tra; trả về mã thoát của bước.
LAST_OUT="$(mktemp "${TMPDIR:-/tmp}/ihouzz_step.XXXXXX")" || exit 1
trap 'rm -f "$LAST_OUT"' EXIT
run_step() {
  local name="$1" rc
  shift
  log "--- BẮT ĐẦU: $name"
  "$@" > "$LAST_OUT" 2>&1
  rc=$?
  cat "$LAST_OUT" >> "$LOG"
  log "--- XONG: $name (mã thoát $rc)"
  return "$rc"
}

# Không cho hai lượt chạy chồng nhau
if command -v flock > /dev/null 2>&1; then
  exec 9> "out/.run_daily.lock"
  if ! flock -n 9; then
    log "BỎ QUA: đang có lượt run_daily.sh khác chạy."
    echo "run_daily.sh: đang có lượt chạy khác, bỏ qua lượt này." >&2
    exit 1
  fi
fi

log "=== BẮT ĐẦU run_daily.sh (thư mục $DIR, Python: $PY) ==="

# --- Kiểm tra biến bắt buộc TRƯỚC khi chạy -------------------------------------------------
# ANTHROPIC_API_KEY cũng bắt buộc: thiếu thì reddit_ingest.py gắn nhãn tạm cho mọi bài, file import
# sẽ rỗng (bài nhãn tạm bị --bo-nhan-tam loại; chúng được giữ lại để lượt sau phân loại lại, không mất).
missing=""
for v in REDDIT_CLIENT_ID REDDIT_CLIENT_SECRET ANTHROPIC_API_KEY; do
  [ -n "${!v:-}" ] || missing="$missing $v"
done
[ -z "$missing" ] || fail 1 "thiếu biến môi trường bắt buộc:$missing (đặt trong file $ENV_FILE)"
[ -n "${REDDIT_USER_AGENT:-}" ] || log "CẢNH BÁO: chưa đặt REDDIT_USER_AGENT; Reddit yêu cầu User-Agent riêng, nên đặt theo INSTALL_IT.md."

# --- 1) Reddit (bắt buộc) ----------------------------------------------------------------
rm -f "$SIGNALS"   # để không bao giờ xuất nhầm file của hôm trước nếu bước này hỏng
reddit_args=(reddit_ingest.py --days 7 --out "$SIGNALS")
[ "${PUSH_LARK:-0}" = "1" ] || reddit_args+=(--no-lark)
run_step "reddit_ingest" "$PY" "${reddit_args[@]}"
rc=$?
# Mã 4 = Reddit trả 403/429: script đã dừng ngay, không thử từ khóa khác (ranh giới dữ liệu số 4).
[ "$rc" -ne 4 ] || fail 4 "Reddit CHẶN truy cập (403/429). Đã dừng, không né. Báo IT kiểm tra app/User-Agent rồi chạy lại sau."
[ "$rc" -eq 0 ] || fail 2 "reddit_ingest.py lỗi (mã $rc)"
[ -f "$SIGNALS" ] || fail 2 "reddit_ingest.py chạy xong nhưng không tạo ra $SIGNALS"
# reddit_ingest.py bỏ qua lỗi mạng/dữ liệu của từng từ khóa; 0 bài + có lỗi nghĩa là Reddit/mạng hỏng chứ không phải "tuần này vắng".
if grep -q 'lỗi khi tìm' "$LAST_OUT" && grep -Eq '(^|[^0-9])0 bài thô' "$LAST_OUT"; then
  fail 2 "Reddit không trả về bài nào và có lỗi khi tìm (kiểm tra mạng, hoặc app chưa được Reddit duyệt)"
fi
n_cls=$(grep -c 'phân loại lỗi' "$LAST_OUT" || true)
[ "${n_cls:-0}" -eq 0 ] || log "CẢNH BÁO: $n_cls bài phân loại AI lỗi, đang mang nhãn tạm: bị loại khỏi file import hôm nay, lượt sau sẽ phân loại lại."

# --- 2) KOSIS (tùy chọn: không bao giờ làm hỏng cả chuỗi) -----------------------------------
USE_STATS=0
KOSIS_NOTE="bỏ qua"
run_step "kosis_ingest" "$PY" kosis_ingest.py --out "$STATS"
rc=$?
case "$rc" in
  0)
    USE_STATS=1
    KOSIS_NOTE="đã lấy"
    ;;
  2)
    log "BỎ QUA KOSIS: chưa cấu hình xong (thiếu KOSIS_API_KEY hoặc mã bảng trong kosis_config.json; xem thông báo ngay phía trên). Không ảnh hưởng các bước khác."
    ;;
  *)
    KOSIS_NOTE="LỖI (mã $rc)"
    log "CẢNH BÁO: KOSIS lỗi (mã $rc), vẫn chạy tiếp. File import lần này KHÔNG có số thống kê KOSIS."
    echo "run_daily.sh CẢNH BÁO: bước KOSIS lỗi, xem $DIR/$LOG" >&2
    ;;
esac

# --- 3) Xuất file import (bắt buộc) -----------------------------------------------------
export_args=(export_for_page.py --in "$SIGNALS" --out "$IMPORT" --bo-nhan-tam)
[ "$USE_STATS" -eq 1 ] && export_args+=(--in "$STATS")
run_step "export_for_page" "$PY" "${export_args[@]}"
rc=$?
if [ "$rc" -ne 0 ]; then
  # Giữ lại bản tín hiệu chưa xuất: lượt Reddit hôm sau sẽ ghi đè $SIGNALS, và các bài này đã bị đánh dấu "đã thấy".
  SAVED="out/reddit_signals_${DAY}_chua_xuat.jsonl"
  cp -f "$SIGNALS" "$SAVED" 2> /dev/null && log "Đã giữ bản tín hiệu chưa xuất tại $SAVED (sau khi sửa lỗi, chạy export_for_page.py --in $SAVED)."
  fail 3 "export_for_page.py lỗi (mã $rc)"
fi

n_lines=$(wc -l < "$IMPORT" | tr -d ' ')
log "KẾT QUẢ: $IMPORT có $n_lines dòng · KOSIS: $KOSIS_NOTE"
log "=== KẾT THÚC run_daily.sh: THÀNH CÔNG ==="
exit 0
