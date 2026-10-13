#!/usr/bin/env bash
# Chạy hằng tuần: (1) Singapore từ ACRA (data.gov.sg), (2) nạp các file CSV danh bạ công khai trong inbox/.
# Mã thoát: lấy mã LỚN NHẤT của hai bước (0 ổn; 1 thiếu cấu hình; 2 nguồn chặn; 3 ghi dở dang; 4 lỗi API).
# Dùng với cron. Xem INSTALL_IT.md.

set -u
cd "$(dirname "$0")" || exit 1
mkdir -p logs inbox/done

stamp() { date '+%Y-%m-%d %H:%M:%S'; }
say() { echo "$(stamp) $*" | tee -a "logs/run_weekly.log"; }

# Không cho hai lần chạy chồng nhau
if command -v flock >/dev/null 2>&1; then
  exec 9>"logs/.lock"
  flock -n 9 || { say "Đang có một lần chạy khác, bỏ qua lần này."; exit 0; }
fi

# Khóa API nằm trong .env (quyền 600), không bao giờ nằm trong code hay cấu hình
if [ ! -f .env ]; then say "THIẾU file .env (xem INSTALL_IT.md mục 3)."; exit 1; fi
perm="$(stat -c '%a' .env 2>/dev/null || echo '?')"
if [ "$perm" != "600" ]; then say "File .env phải có quyền 600 (hiện là $perm). Chạy: chmod 600 .env"; exit 1; fi
set -a
# shellcheck disable=SC1091
. ./.env
set +a

PY="python3"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"

# Tự kiểm offline trước khi gọi ra ngoài; hỏng thì dừng
"$PY" sg_acra_scan.py --self-test >/dev/null 2>&1 || { say "Tự kiểm sg_acra_scan.py thất bại, dừng."; exit 1; }
"$PY" import_directory.py --self-test >/dev/null 2>&1 || { say "Tự kiểm import_directory.py thất bại, dừng."; exit 1; }

worst=0

say "Bắt đầu: Singapore (ACRA)"
"$PY" sg_acra_scan.py
rc=$?
say "Singapore (ACRA) xong, mã thoát $rc"
[ "$rc" -gt "$worst" ] && worst=$rc

say "Bắt đầu: nạp danh bạ công khai trong inbox/"
"$PY" import_directory.py
rc=$?
say "Nạp danh bạ xong, mã thoát $rc"
[ "$rc" -gt "$worst" ] && worst=$rc

say "Kết thúc, mã thoát chung $worst"
echo "$(stamp) $worst" > logs/last_exit_code.txt
exit "$worst"
