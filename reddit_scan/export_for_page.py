#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_for_page.py — Gom đầu ra của các script thu thập thành MỘT file JSONL
đúng định dạng IMPORT_SPEC.md, để người vận hành nạp vào trang nội bộ.

Đọc:   out/reddit_signals.jsonl   (từ reddit_ingest.py)
       out/kosis_stats.jsonl      (từ kosis_ingest.py, nếu có)
       out/orgs.jsonl             (đầu mối tổ chức, nếu có; hiện chưa có script nào tạo)
Ghi:   out/import_YYYYMMDD.jsonl  (YYYYMMDD = ngày hôm nay theo giờ Hàn Quốc)
       Nếu file đó đã có (chạy lại trong ngày) thì GIỮ dòng cũ và chỉ thêm dòng mới; muốn ghi đè dùng --ghi-de.

Mỗi dòng được kiểm tra theo "Quy tắc bất biến" của IMPORT_SPEC.md. Dòng sai thì
BỎ (không sửa lén), lý do in ra stderr, cuối cùng in tổng kết "giữ N, bỏ M".

Lớp bảo vệ ở đây là lớp thứ hai (đã có ẩn danh ở reddit_ingest.py); trang nhận file
sẽ kiểm tra lần thứ ba.

Dùng:
    python3 export_for_page.py                      # đọc file mặc định, ghi out/import_<hôm nay>.jsonl
    python3 export_for_page.py --in a.jsonl --in b.jsonl --out out/import_20261013.jsonl
    python3 export_for_page.py --kiem-tra out/import_20261013.jsonl   # chỉ kiểm tra, không ghi
    python3 export_for_page.py --self-test          # chạy thử offline

Mã thoát: 0 = xong; 1 = lỗi đọc/ghi file hoặc (với --kiem-tra) có dòng sai;
          2 = không tìm thấy file đầu vào nào.
"""

import argparse
import datetime as dt
import io
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reddit_ingest import anonymize  # noqa: E402  (dùng lại đúng hàm ẩn danh đã có)

# ----------------------------------------------------------------------------
# HỢP ĐỒNG ĐẦU RA (sao từ IMPORT_SPEC.md — sửa spec thì sửa ở đây)
# ----------------------------------------------------------------------------
KINDS = ("signal", "stat", "org")

# Khóa danh tính: chỉ cần tên khóa (viết thường) CHỨA một trong các đoạn này là bị từ chối.
# Gồm các khóa nêu trong spec (author, username, user, profile, member(s), friend,
# email_nguoi_dang, link_nguoi_dang, permalink_nguoi_dang) và vài tên cùng nghĩa.
FORBIDDEN_KEY_PARTS = ("author", "user", "profile", "member", "friend",
                       "nguoi_dang", "permalink", "redditor", "handle")

CHU_DE = ["Tài chính và gửi tiền", "Nhà đất tại VN", "Việc làm và visa",
          "Đời sống tại Hàn", "Học tập", "Về nước, định cư", "Gia đình", "Khác"]
NHU_CAU = ["Có", "Không", "Chỉ bàn luận"]
MUC_CU_THE = ["Hỏi chung", "Có ngân sách", "Có địa điểm", "Có thời điểm"]
NHOM_NGUOI = ["Lao động", "Du học", "Kết hôn, định cư", "Chuyên gia",
              "Chủ doanh nghiệp", "Không rõ"]
NGON_NGU = ["Tiếng Việt", "Lẫn tiếng Hàn", "Khác"]
SAC_THAI = ["Tích cực", "Trung tính", "Lo lắng, bức xúc"]

AREAS = ["Toàn quốc", "Seoul", "Busan", "Incheon", "Daegu", "Daejeon", "Gwangju",
         "Ulsan", "Sejong", "Gyeonggi", "Gangwon", "Chungcheong Bắc",
         "Chungcheong Nam", "Jeolla Bắc", "Jeolla Nam", "Gyeongsang Bắc",
         "Gyeongsang Nam", "Jeju"]
CONFIDENCE = ["chính thức", "thứ cấp"]
ORG_TYPES = ["Hội đoàn", "Doanh nghiệp Việt tại Hàn", "Tổ chức phía Việt Nam", "Nhóm, kênh"]

# Thứ tự khóa khi ghi ra (chỉ các khóa này được ghi; khóa lạ không nguy hiểm bị bỏ khỏi dòng)
SIGNAL_KEYS = ["kind", "source", "subreddit", "ngay_dang", "tuan", "matched_keyword",
               "chu_de", "nhu_cau_ro", "muc_cu_the", "dia_phuong_vn", "noi_o_tai_han",
               "nhom_nguoi", "ngon_ngu", "sac_thai", "la_quang_cao", "trich_doan"]
STAT_KEYS = ["kind", "metric", "area", "period", "value", "female", "src", "confidence"]
ORG_KEYS = ["kind", "name", "type", "province", "subarea", "phone", "email", "web",
            "fb", "zalo", "yt", "addr", "src"]

MAX_EXCERPT = 200
ANON_REMAINS = [re.compile(p) for p in (
    r"[\w.+-]+@[\w-]+\.[\w.-]+", r"https?://", r"www\.", r"(?<![\w])/?u/[A-Za-z0-9_\-]+")]

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WEEK = re.compile(r"^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$")
_PERIOD = re.compile(r"^\d{4}(-(0[1-9]|1[0-2]))?$")
_METRIC = re.compile(r"^[a-z0-9_]{1,60}$")
_SUBREDDIT = re.compile(r"^[A-Za-z0-9_]{1,40}$")

# Trang cá nhân hay lộ trong ô liên hệ của tổ chức
_PERSONAL_LINK = re.compile(r"(reddit\.com/(u|user)/|profile\.php|facebook\.com/people/|/people/)", re.I)

KST = dt.timezone(dt.timedelta(hours=9))  # Hàn Quốc không có giờ mùa hè


class Reject(Exception):
    """Dòng bị từ chối; .args[0] là lý do (tiếng Việt, ngắn)."""


# ----------------------------------------------------------------------------
# TIỆN ÍCH KIỂM TRA
# ----------------------------------------------------------------------------
def _short(v, n=40):
    s = str(v).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def _nfc(v):
    """Chuẩn hóa chuỗi Unicode về một dạng (tránh 'chính thức' gõ khác dạng bị coi là sai)."""
    return unicodedata.normalize("NFC", v).strip() if isinstance(v, str) else v


def find_forbidden_key(obj):
    """Trả về tên khóa danh tính đầu tiên tìm thấy (kể cả khóa lồng bên trong), hoặc None."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            low = str(k).lower()
            if any(part in low for part in FORBIDDEN_KEY_PARTS):
                return str(k)
            sub = find_forbidden_key(v)
            if sub:
                return sub
    elif isinstance(obj, list):
        for v in obj:
            sub = find_forbidden_key(v)
            if sub:
                return sub
    return None


def _req_str(row, key, max_len=200, allow_empty=False):
    v = row.get(key)
    if not isinstance(v, str):
        if v is None and allow_empty:
            return ""
        raise Reject(f"'{key}' phải là chữ" + (" (đang thiếu)" if v is None else ""))
    v = _nfc(v)
    if not v and not allow_empty:
        raise Reject(f"'{key}' đang trống")
    if len(v) > max_len:
        raise Reject(f"'{key}' dài quá {max_len} ký tự")
    return v


def _enum(row, key, allowed):
    v = _nfc(row.get(key))
    if not isinstance(v, str) or v not in allowed:
        raise Reject(f"'{key}' không hợp lệ: '{_short(row.get(key))}'")
    return v


def _free_text(row, key, max_len, allow_empty=True):
    """Chữ tự do do AI/người nhập: ẩn danh lại và cắt gọn (không từ chối vì quá dài)."""
    v = row.get(key)
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise Reject(f"'{key}' phải là chữ")
    v = anonymize(_nfc(v))
    if len(v) > max_len:
        v = v[: max_len - 1] + "…"
    if not v and not allow_empty:
        raise Reject(f"'{key}' đang trống")
    return v


def _nonneg_int(row, key, required):
    v = row.get(key)
    if v is None:
        if required:
            raise Reject(f"thiếu '{key}'")
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        raise Reject(f"'{key}' phải là số nguyên: '{_short(v)}'")
    if v < 0:
        raise Reject(f"'{key}' không được âm")
    return v


# ----------------------------------------------------------------------------
# KIỂM TRA TỪNG LOẠI DÒNG
# ----------------------------------------------------------------------------
def check_signal(row):
    out = {"kind": "signal"}
    out["source"] = _req_str(row, "source", 40)

    sub = _req_str(row, "subreddit", 40, allow_empty=True)
    if sub:
        if sub.lower().startswith(("u_", "u/")):
            raise Reject("subreddit là trang cá nhân của một người (u_...)")
        if not _SUBREDDIT.match(sub):
            raise Reject(f"'subreddit' không đúng dạng: '{_short(sub)}'")
    out["subreddit"] = sub

    day = _req_str(row, "ngay_dang", 10)
    try:
        if not _DATE.match(day):
            raise ValueError
        d = dt.datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        raise Reject(f"'ngay_dang' phải là YYYY-MM-DD: '{_short(day)}'")
    out["ngay_dang"] = day

    tuan = row.get("tuan")
    if tuan in (None, ""):
        iso = d.isocalendar()
        tuan = f"{iso[0]}-W{iso[1]:02d}"
    tuan = _nfc(tuan)
    if not isinstance(tuan, str) or not _WEEK.match(tuan):
        raise Reject(f"'tuan' phải có dạng YYYY-Www: '{_short(tuan)}'")
    out["tuan"] = tuan

    out["matched_keyword"] = _free_text(row, "matched_keyword", 80)
    out["chu_de"] = _enum(row, "chu_de", CHU_DE)
    out["nhu_cau_ro"] = _enum(row, "nhu_cau_ro", NHU_CAU)
    out["muc_cu_the"] = _enum(row, "muc_cu_the", MUC_CU_THE)
    out["dia_phuong_vn"] = _free_text(row, "dia_phuong_vn", 80)
    out["noi_o_tai_han"] = _free_text(row, "noi_o_tai_han", 80)
    out["nhom_nguoi"] = _enum(row, "nhom_nguoi", NHOM_NGUOI)
    out["ngon_ngu"] = _enum(row, "ngon_ngu", NGON_NGU)
    out["sac_thai"] = _enum(row, "sac_thai", SAC_THAI)

    # la_quang_cao = true đã bị loại ở bước chung; ở đây bắt buộc phải là false rõ ràng
    if row.get("la_quang_cao") is not False:
        raise Reject("thiếu 'la_quang_cao' hoặc không phải true/false (không chắc có phải quảng cáo)")
    out["la_quang_cao"] = False

    # trich_doan: ẩn danh lại, ép <= 200 ký tự
    raw = row.get("trich_doan")
    if not isinstance(raw, str):
        raise Reject("thiếu 'trich_doan'")
    t = anonymize(_nfc(raw))
    if len(t) > MAX_EXCERPT:
        t = t[: MAX_EXCERPT - 1] + "…"
    if not t:
        raise Reject("'trich_doan' trống")
    if any(p.search(t) for p in ANON_REMAINS):
        raise Reject("'trich_doan' vẫn còn email/link/u-handle sau khi ẩn danh")
    out["trich_doan"] = t
    return out


def check_stat(row):
    out = {"kind": "stat"}
    metric = _req_str(row, "metric", 60)
    if not _METRIC.match(metric):
        raise Reject(f"'metric' không đúng dạng (chữ thường, số, gạch dưới): '{_short(metric)}'")
    out["metric"] = metric
    out["area"] = _enum(row, "area", AREAS)

    period = _req_str(row, "period", 7)
    if not _PERIOD.match(period):
        raise Reject(f"'period' phải là YYYY hoặc YYYY-MM: '{_short(period)}'")
    out["period"] = period

    out["value"] = _nonneg_int(row, "value", required=True)
    female = _nonneg_int(row, "female", required=False)
    if female is not None:
        if female > out["value"]:
            raise Reject("'female' lớn hơn 'value'")
        out["female"] = female

    out["src"] = _req_str(row, "src", 500)
    conf = _enum(row, "confidence", CONFIDENCE)
    if conf == "chính thức" and "http" not in out["src"].lower():
        raise Reject("confidence 'chính thức' nhưng 'src' không có link")
    out["confidence"] = conf
    return out


def check_org(row):
    out = {"kind": "org"}
    out["name"] = _req_str(row, "name", 200)
    out["type"] = _enum(row, "type", ORG_TYPES)
    prov = _nfc(row.get("province")) or ""
    if prov and prov not in AREAS:
        raise Reject(f"'province' không hợp lệ: '{_short(prov)}'")
    out["province"] = prov
    for key, n in (("subarea", 100), ("phone", 40), ("email", 120), ("web", 300),
                   ("fb", 300), ("zalo", 100), ("yt", 300), ("addr", 300)):
        out[key] = _req_str(row, key, n, allow_empty=True)
    for key in ("web", "fb", "zalo", "yt"):
        if _PERSONAL_LINK.search(out[key]):
            raise Reject(f"'{key}' có vẻ là trang cá nhân, chỉ nhận trang của tổ chức")
    src = _req_str(row, "src", 500)
    if not src.lower().startswith(("http://", "https://")):
        raise Reject("'src' của tổ chức phải là link trang chính thức")
    out["src"] = src
    return out


CHECKERS = {"signal": (check_signal, SIGNAL_KEYS), "stat": (check_stat, STAT_KEYS),
            "org": (check_org, ORG_KEYS)}


def _guess_kind(row):
    """Đoán loại dòng chỉ để in lý do cho dễ đọc (không dùng để quyết định giữ/bỏ)."""
    if not isinstance(row, dict):
        return "?"
    k = _nfc(row.get("kind"))
    if k in KINDS:
        return k
    return "signal" if (not k and "chu_de" in row) else "?"


def validate_row(row, drop_provisional=False):
    """Kiểm tra một dòng đã đọc từ JSON.
    Trả về (loại, dòng_sạch). Ném Reject(lý do) nếu phải bỏ; Reject có thuộc tính .kind."""
    try:
        if not isinstance(row, dict):
            raise Reject("dòng không phải một đối tượng JSON")

        bad = find_forbidden_key(row)
        if bad:
            raise Reject(f"có khóa danh tính '{_short(bad)}'")

        kind = _nfc(row.get("kind"))
        if kind is None or kind == "":
            if "chu_de" in row:
                kind = "signal"
            else:
                raise Reject("thiếu 'kind' (và không phải dạng tín hiệu)")
        if kind not in KINDS:
            raise Reject(f"loại '{_short(kind)}' không được nhận (chỉ signal/stat/org)")

        if row.get("la_quang_cao") is True:
            raise Reject("quảng cáo (la_quang_cao=true)")
        if drop_provisional and row.get("_nhan_tam"):
            raise Reject("nhãn tạm (chưa được AI phân loại thật)")
        checker, _keys = CHECKERS[kind]
        return kind, checker(row)
    except Reject as e:
        e.kind = _guess_kind(row)
        raise


# ----------------------------------------------------------------------------
# ĐỌC / GHI
# ----------------------------------------------------------------------------
def iter_jsonl(path):
    """Sinh (số_dòng, giá_trị | Reject)."""
    with open(path, encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield n, json.loads(line)
            except ValueError:
                yield n, Reject("không đọc được JSON")


def process(inputs, drop_provisional=False, err=sys.stderr):
    """Đọc các file đầu vào, trả về (danh_sách_dòng_sạch, thống_kê)."""
    kept_rows = []
    stats = {"keep": {}, "drop": {}, "reasons": {}, "files_missing": []}
    for path in inputs:
        if not os.path.exists(path):
            stats["files_missing"].append(path)
            continue
        for n, val in iter_jsonl(path):
            kind = "?"
            try:
                if isinstance(val, Reject):
                    raise val
                kind, clean = validate_row(val, drop_provisional)
                kept_rows.append(clean)
                stats["keep"][kind] = stats["keep"].get(kind, 0) + 1
            except Reject as e:
                kind = getattr(e, "kind", kind)
                reason = e.args[0]
                print(f"  - bỏ {os.path.basename(path)}:{n} [{kind}] {reason}", file=err)
                stats["drop"][kind] = stats["drop"].get(kind, 0) + 1
                key = re.sub(r": '[^']*'$", "", reason)  # gom lý do giống nhau (bỏ giá trị cụ thể)
                key = re.sub(r"(khóa danh tính) '[^']*'$", r"\1", key)
                stats["reasons"][key] = stats["reasons"].get(key, 0) + 1
    return kept_rows, stats


def dedupe(rows):
    """Bỏ dòng trùng y hệt, giữ thứ tự xuất hiện đầu tiên."""
    seen, out = set(), []
    for r in rows:
        k = json.dumps(r, sort_keys=True, ensure_ascii=False)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def write_jsonl_atomic(rows, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            keys = CHECKERS[r["kind"]][1]
            f.write(json.dumps({k: r[k] for k in keys if k in r}, ensure_ascii=False) + "\n")
    os.replace(tmp, path)  # người vận hành không bao giờ thấy file ghi dở


def summary_text(stats):
    keep, drop = sum(stats["keep"].values()), sum(stats["drop"].values())
    parts = []
    for k in KINDS + ("?",):
        if stats["keep"].get(k) or stats["drop"].get(k):
            label = k if k != "?" else "không rõ loại"
            parts.append(f"{label}: giữ {stats['keep'].get(k, 0)}, bỏ {stats['drop'].get(k, 0)}")
    s = f"Tổng kết: giữ {keep}, bỏ {drop}" + (f"  ({' · '.join(parts)})" if parts else "")
    if stats["reasons"]:
        s += "\n  Lý do bỏ: " + " · ".join(f"{r} ×{c}" for r, c in
                                         sorted(stats["reasons"].items(), key=lambda x: -x[1]))
    return s


def today_kst():
    return dt.datetime.now(KST).strftime("%Y%m%d")


DEFAULT_INPUTS = ["out/reddit_signals.jsonl", "out/kosis_stats.jsonl", "out/orgs.jsonl"]


def run(args, err=sys.stderr, out=sys.stdout):
    if args.kiem_tra:
        inputs, out_path = [args.kiem_tra], None
    else:
        inputs = args.inputs or DEFAULT_INPUTS
        out_path = args.out or f"out/import_{args.date or today_kst()}.jsonl"

    if not any(os.path.exists(p) for p in inputs):
        print("LỖI: không tìm thấy file đầu vào nào: " + ", ".join(inputs) +
              "\n     (chạy reddit_ingest.py trước, hoặc chỉ đúng file bằng --in)", file=err)
        return 2

    try:
        rows, stats = process(inputs, args.bo_nhan_tam, err)
        for p in stats["files_missing"]:
            print(f"  (không có file {p}, bỏ qua)", file=err)
        n_old, n_valid = 0, len(rows)
        if out_path:
            # Chạy lại trong cùng ngày: giữ các dòng đã có trong file hôm nay (kiểm tra lại từng dòng),
            # chỉ thêm dòng mới. Tránh mất tín hiệu khi lượt chạy sau không còn bài mới (bài cũ đã "đã thấy").
            old = []
            if os.path.exists(out_path) and not getattr(args, "ghi_de", False):
                old, _ = process([out_path], False, io.StringIO())
            old = dedupe(old)
            n_old = len(old)
            rows = dedupe(old + rows)
            write_jsonl_atomic(rows, out_path)
    except OSError as e:
        print(f"LỖI đọc/ghi file: {e}", file=err)
        return 1

    print(summary_text(stats), file=err)
    n_drop = sum(stats["drop"].values())
    if not rows and n_drop:
        print("  ! TẤT CẢ dòng đều bị bỏ — xem lý do ở trên trước khi đưa file cho người vận hành.",
              file=err)
    if out_path:
        notes = []
        if n_old:
            notes.append(f"{n_old} dòng có sẵn từ lần chạy trước trong ngày được giữ lại")
        if n_old + n_valid > len(rows):
            notes.append(f"gộp {n_old + n_valid - len(rows)} dòng trùng")
        print(f"Đã ghi {out_path}: {len(rows)} dòng, thêm mới {len(rows) - n_old}"
              + ("; " + "; ".join(notes) if notes else "") + ".", file=out)
        return 0
    print("Chế độ kiểm tra: không ghi file.", file=out)
    return 1 if n_drop else 0


# ----------------------------------------------------------------------------
# CHẠY THỬ OFFLINE
# ----------------------------------------------------------------------------
def self_test():
    import io
    import tempfile
    import reddit_ingest as ri

    # Hợp đồng enum ở đây phải trùng bộ nhãn mà reddit_ingest.py đang bắt AI dùng
    for name in ("CHU_DE", "NHU_CAU", "MUC_CU_THE", "NHOM_NGUOI", "NGON_NGU", "SAC_THAI"):
        assert globals()[name] == getattr(ri, name), f"enum {name} lệch giữa 2 file"

    good_signal = {
        "source": "reddit", "subreddit": "korea", "ngay_dang": "2026-10-12", "tuan": "2026-W42",
        "matched_keyword": "gửi tiền về", "chu_de": "Tài chính và gửi tiền",
        "nhu_cau_ro": "Chỉ bàn luận", "muc_cu_the": "Hỏi chung", "dia_phuong_vn": "",
        "noi_o_tai_han": "Ansan", "nhom_nguoi": "Lao động", "ngon_ngu": "Tiếng Việt",
        "sac_thai": "Trung tính", "la_quang_cao": False,
        "trich_doan": "Hỏi cách gửi tiền về Việt Nam ít phí",
    }
    good_stat = {  # SỐ GIẢ để thử logic, không phải số thật
        "kind": "stat", "metric": "nguoi_viet_theo_tinh", "area": "Gyeonggi", "period": "2026-09",
        "value": 1000, "female": 600, "confidence": "chính thức",
        "src": "KOSIS · [GIẢ LẬP] bảng thử · https://kosis.kr/statHtml/statHtml.do?orgId=TEST&tblId=TEST"}
    good_org = {"kind": "org", "name": "Tổ chức thử nghiệm", "type": "Hội đoàn", "province": "Gyeonggi",
                "subarea": "Ansan", "phone": "", "email": "", "web": "https://example.org",
                "fb": "", "zalo": "", "yt": "", "addr": "", "src": "https://example.org/lien-he"}

    def sig(**kw):
        d = dict(good_signal)
        d.update(kw)
        return d

    long_text = "Gửi tiền về quê " + "rất nhiều lần " * 30 + "liên hệ a@b.com"
    lines = [
        # --- phải GIỮ (8) ---
        sig(),                                                              # 1 không có kind, có chu_de -> signal
        sig(kind="signal", ngay_dang="2026-10-11", tuan="2026-W41"),         # 2
        sig(trich_doan="Gọi 010-2957-4821 hoặc mail a@b.com, xem https://x.co/y, hỏi u/seller_1"),  # 3 phải được ẩn danh lại
        sig(trich_doan=long_text),                                          # 4 phải bị cắt <= 200
        {**sig(trich_doan="Bài mang nhãn tạm"), "_nhan_tam": True, "x_khac": "khóa lạ vô hại"},  # 5 khóa lạ bị lược, vẫn giữ
        good_stat,                                                          # 6
        good_org,                                                           # 7
        {**good_stat, "area": "Toàn quốc", "period": "2026", "female": None, "value": 5},  # 8 female None = bỏ qua
        # --- phải BỎ (13) ---
        {**sig(), "author": "someone"},                                     # có khóa danh tính
        {**sig(), "Username": "x"},                                         # viết hoa vẫn bị bắt
        {**sig(), "permalink_nguoi_dang": "https://x"},
        {**sig(), "meta": {"profile": "z"}},                                # khóa lồng bên trong
        sig(la_quang_cao=True),                                             # quảng cáo
        {**good_stat, "la_quang_cao": True},                                # quảng cáo ở loại khác cũng bỏ
        sig(chu_de="Linh tinh"),                                            # enum sai
        sig(sac_thai="vui"),                                                # enum sai
        sig(kind="ca_nhan"),                                                # loại không được nhận
        sig(subreddit="u_someone"),                                         # trang cá nhân
        {k: v for k, v in sig().items() if k != "la_quang_cao"},            # thiếu la_quang_cao
        "dòng này không phải JSON {{{",
        {**good_stat, "area": "Tokyo"},                                     # area sai
    ]
    more_bad = [
        {**good_stat, "value": -3}, {**good_stat, "value": 12.5}, {**good_stat, "value": True},
        {**good_stat, "period": "2026-13"}, {**good_stat, "female": 2000},
        {**good_stat, "src": "KOSIS bảng thử (không link)"},
        {**good_stat, "confidence": "đoán"}, {**good_stat, "src": ""},
        {**good_org, "src": ""}, {**good_org, "type": "Cá nhân"},
        {**good_org, "fb": "https://facebook.com/profile.php?id=123"},
        {**good_org, "member": "x"},
    ]
    EXPECT_KEEP = 8
    EXPECT_DROP = 13 + len(more_bad)

    with tempfile.TemporaryDirectory() as tmp:
        src_a = os.path.join(tmp, "signals.jsonl")
        src_b = os.path.join(tmp, "stats.jsonl")
        with open(src_a, "w", encoding="utf-8") as f:
            for r in lines:
                f.write((r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)) + "\n")
            f.write("\n")  # dòng trống bị bỏ qua, không tính
        with open(src_b, "w", encoding="utf-8") as f:
            for r in more_bad:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        out_path = os.path.join(tmp, "import_test.jsonl")
        ns = argparse.Namespace(inputs=[src_a, src_b], out=out_path, date=None,
                                kiem_tra=None, bo_nhan_tam=False)
        err, outb = io.StringIO(), io.StringIO()
        code = run(ns, err, outb)
        text = err.getvalue()
        assert code == 0, (code, text)
        assert f"giữ {EXPECT_KEEP}, bỏ {EXPECT_DROP}" in text, text

        with open(out_path, encoding="utf-8") as f:
            raw_lines = f.read().splitlines()
        rows = [json.loads(x) for x in raw_lines]
        assert len(rows) == EXPECT_KEEP, len(rows)
        for r in rows:
            assert r["kind"] in KINDS
            assert find_forbidden_key(r) is None
            assert list(r.keys())[0] == "kind"
            if r["kind"] == "signal":
                assert len(r["trich_doan"]) <= MAX_EXCERPT
                assert not any(p.search(r["trich_doan"]) for p in ANON_REMAINS)
                assert "4821" not in r["trich_doan"]
                assert r["la_quang_cao"] is False
                assert "_nhan_tam" not in r and "x_khac" not in r
        assert rows[0]["kind"] == "signal"                       # kind được thêm cho dòng thiếu kind
        assert "4821" not in rows[2]["trich_doan"] and "[đã ẩn]" in rows[2]["trich_doan"]
        assert len(rows[3]["trich_doan"]) == MAX_EXCERPT and rows[3]["trich_doan"].endswith("…")
        assert rows[7]["area"] == "Toàn quốc" and "female" not in rows[7]   # female=None không ghi ra
        # lý do bỏ phải được in ra stderr
        for needle in ("có khóa danh tính", "quảng cáo", "'chu_de' không hợp lệ",
                       "không được nhận", "không đọc được JSON", "'area' không hợp lệ",
                       "trang cá nhân", "'src' không có link"):
            assert needle in text, f"thiếu lý do: {needle}"
        # lý do không được in giá trị của khóa danh tính
        assert "someone" not in text

        # chạy lại cho kết quả y hệt (nạp lại không sinh khác biệt)
        out2 = os.path.join(tmp, "import_test2.jsonl")
        ns.out = out2
        run(ns, io.StringIO(), io.StringIO())
        with open(out_path, "rb") as a, open(out2, "rb") as b:
            assert a.read() == b.read(), "chạy lại ra kết quả khác"

        # chạy lại vào CÙNG file trong ngày: dòng cũ được giữ, không nhân đôi
        with open(out_path, "rb") as f:
            before = f.read()
        same = argparse.Namespace(inputs=[src_a, src_b], out=out_path, date=None,
                                  kiem_tra=None, bo_nhan_tam=False)
        run(same, io.StringIO(), io.StringIO())
        with open(out_path, "rb") as f:
            assert f.read() == before, "chạy lại vào cùng file làm đổi nội dung"
        src_c = os.path.join(tmp, "moi.jsonl")
        with open(src_c, "w", encoding="utf-8") as f:
            f.write(json.dumps(sig(trich_doan="Một bài mới hoàn toàn"), ensure_ascii=False) + "\n")
        o5 = io.StringIO()
        run(argparse.Namespace(inputs=[src_c], out=out_path, date=None, kiem_tra=None, bo_nhan_tam=False),
            io.StringIO(), o5)
        with open(out_path, "rb") as f:
            after = f.read()
        assert after.startswith(before) and after.count(b"\n") == EXPECT_KEEP + 1, "dòng cũ bị mất khi chạy lại"
        assert f"thêm mới 1" in o5.getvalue(), o5.getvalue()
        run(argparse.Namespace(inputs=[src_c], out=out_path, date=None, kiem_tra=None, bo_nhan_tam=False,
                               ghi_de=True), io.StringIO(), io.StringIO())
        with open(out_path, "rb") as f:
            assert f.read().count(b"\n") == 1, "--ghi-de phải ghi đè"
        src_d = os.path.join(tmp, "trung.jsonl")
        with open(src_d, "w", encoding="utf-8") as f:
            f.write(json.dumps(good_stat) + "\n" + json.dumps(good_stat) + "\n")
        o6, d_path = io.StringIO(), os.path.join(tmp, "dup.jsonl")
        run(argparse.Namespace(inputs=[src_d], out=d_path, date=None, kiem_tra=None, bo_nhan_tam=False),
            io.StringIO(), o6)
        with open(d_path, "rb") as f:
            assert f.read().count(b"\n") == 1 and "gộp 1 dòng trùng" in o6.getvalue(), o6.getvalue()
        with open(out_path, "wb") as f:  # trả lại file như trước cho các bước sau
            f.write(before)

        # --bo-nhan-tam: dòng số 5 bị bỏ
        ns.out, ns.bo_nhan_tam = os.path.join(tmp, "import_test3.jsonl"), True
        e3 = io.StringIO()
        run(ns, e3, io.StringIO())
        assert f"giữ {EXPECT_KEEP - 1}, bỏ {EXPECT_DROP + 1}" in e3.getvalue(), e3.getvalue()

        # --kiem-tra trên file đã xuất: sạch hoàn toàn, mã thoát 0
        ns2 = argparse.Namespace(inputs=None, out=None, date=None, kiem_tra=out_path, bo_nhan_tam=False)
        e4 = io.StringIO()
        assert run(ns2, e4, io.StringIO()) == 0, e4.getvalue()
        assert "bỏ 0" in e4.getvalue()
        # --kiem-tra trên file đầu vào lẫn dòng sai: mã thoát 1
        ns2.kiem_tra = src_a
        assert run(ns2, io.StringIO(), io.StringIO()) == 1

        # không có file đầu vào -> mã 2
        ns3 = argparse.Namespace(inputs=[os.path.join(tmp, "khong_co.jsonl")], out=out_path,
                                 date=None, kiem_tra=None, bo_nhan_tam=False)
        assert run(ns3, io.StringIO(), io.StringIO()) == 2

    print("self-test: OK — giữ đúng 8 dòng hợp lệ, bỏ đúng 25 dòng sai "
          "(khóa danh tính, quảng cáo, enum sai, loại lạ, trang cá nhân, thiếu link...).")


def main():
    p = argparse.ArgumentParser(description="Xuất file import cho trang nội bộ (IMPORT_SPEC.md).")
    p.add_argument("--in", dest="inputs", action="append", metavar="FILE",
                   help="file JSONL đầu vào (dùng nhiều lần được). Mặc định: " + ", ".join(DEFAULT_INPUTS))
    p.add_argument("--out", help="file xuất. Mặc định out/import_YYYYMMDD.jsonl (ngày theo giờ Hàn Quốc)")
    p.add_argument("--date", help="YYYYMMDD dùng đặt tên file xuất (mặc định: hôm nay giờ Hàn Quốc)")
    p.add_argument("--ghi-de", action="store_true",
                   help="ghi đè file xuất nếu đã có (mặc định: giữ dòng cũ trong file và chỉ thêm dòng mới)")
    p.add_argument("--bo-nhan-tam", action="store_true",
                   help="bỏ các dòng mang nhãn tạm (_nhan_tam) do chưa có AI phân loại thật")
    p.add_argument("--kiem-tra", metavar="FILE",
                   help="chỉ kiểm tra một file import có sẵn, không ghi gì; thoát mã 1 nếu có dòng sai")
    p.add_argument("--self-test", action="store_true", help="chạy thử offline")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.date and not re.fullmatch(r"\d{8}", args.date):
        p.error("--date phải có dạng YYYYMMDD")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
