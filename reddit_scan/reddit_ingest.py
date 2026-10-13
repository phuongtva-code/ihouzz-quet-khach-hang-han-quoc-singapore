#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reddit_ingest.py — Lấy tín hiệu nhu cầu (lớp 3) từ Reddit cho dự án
"Quét cộng đồng người Việt tại Hàn Quốc" của iHouzz.

Nguyên tắc (giữ đúng ranh giới dự án):
  - Chỉ đọc nội dung CÔNG KHAI qua Reddit API chính thức (OAuth script app).
  - KHÔNG lưu tác giả, username, link, ảnh đại diện hay bất kỳ định danh cá nhân nào.
  - Ẩn danh ngay trước khi phân loại: bỏ email, số điện thoại, URL, u/handle.
  - Chỉ lưu tín hiệu đã gắn nhãn + trích đoạn <= 200 ký tự đã ẩn danh.
  - Đây là LỚP 3 (cộng đồng đang bàn gì), không tạo đầu mối cá nhân.

Pipeline: thu thập -> làm sạch/ẩn danh -> AI phân loại (Claude) -> lưu
(JSONL cục bộ, và tùy chọn đẩy sang Lark Base).

Chạy thử không cần key:
    python3 reddit_ingest.py --self-test

Chạy thật:
    export REDDIT_CLIENT_ID=...  REDDIT_CLIENT_SECRET=...  REDDIT_USER_AGENT="ihouzz-scan/0.1 by u/xxx"
    export ANTHROPIC_API_KEY=...            # để AI phân loại; thiếu thì dùng nhãn tạm
    python3 reddit_ingest.py --days 7 --limit 60 --out out/reddit_signals.jsonl

Mã thoát:  0 = xong · 1 = thiếu thư viện/khóa, khóa Reddit sai (401)
           4 = Reddit chặn (403/429): dừng ngay, KHÔNG né, báo IT rồi chạy lại sau

Bài chỉ được ghi vào danh sách "đã thấy" (--seen) khi đã phân loại thật thành công.
Bài mang nhãn tạm (thiếu khóa, AI lỗi) sẽ được thử lại ở lượt sau, không mất.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time

# ----------------------------------------------------------------------------
# CẤU HÌNH — chỉnh ở đây
# ----------------------------------------------------------------------------
# Các subreddit nơi có thể bắt gặp thảo luận của người Việt ở Hàn / về Hàn.
# Lưu ý thực tế: cộng đồng người Việt tại Hàn chủ yếu ở Facebook/Zalo, nên
# lượng tín hiệu trên Reddit sẽ MỎNG. Reddit dùng để dựng và kiểm chứng pipeline.
SUBREDDITS = [
    "korea", "Living_in_Korea", "hanguk", "koreatravel",
    "vietnam", "VietNam",
]

# Từ khóa tìm kiếm (tiếng Việt + vài từ tiếng Anh thường gặp).
KEYWORDS = [
    "người Việt Hàn Quốc", "gửi tiền về", "mua đất quê", "mua nhà Việt Nam",
    "xây nhà cho bố mẹ", "về nước", "EPS", "visa E-9", "cô dâu Hàn",
    "du học Hàn", "xuất khẩu lao động Hàn", "Vietnamese Korea remittance",
]

# Bộ nhãn (khớp từ điển chỉ số của dự án).
CHU_DE = ["Tài chính và gửi tiền", "Nhà đất tại VN", "Việc làm và visa",
          "Đời sống tại Hàn", "Học tập", "Về nước, định cư", "Gia đình", "Khác"]
NHU_CAU = ["Có", "Không", "Chỉ bàn luận"]
MUC_CU_THE = ["Hỏi chung", "Có ngân sách", "Có địa điểm", "Có thời điểm"]
NHOM_NGUOI = ["Lao động", "Du học", "Kết hôn, định cư", "Chuyên gia",
              "Chủ doanh nghiệp", "Không rõ"]
NGON_NGU = ["Tiếng Việt", "Lẫn tiếng Hàn", "Khác"]
SAC_THAI = ["Tích cực", "Trung tính", "Lo lắng, bức xúc"]

ANON = "[đã ẩn]"
DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# ----------------------------------------------------------------------------
# LÀM SẠCH / ẨN DANH
# ----------------------------------------------------------------------------
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL = re.compile(r"(https?://\S+|www\.\S+)", re.I)
_USER = re.compile(r"(?<![\w])/?u/[A-Za-z0-9_\-]+")          # u/handle, /u/handle
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s().\-]{7,}\d)")       # số dài >= 9 chữ số
_WS = re.compile(r"\s+")


def anonymize(text):
    """Bỏ mọi định danh cá nhân khỏi văn bản công khai."""
    if not text:
        return ""
    t = _EMAIL.sub(ANON, text)
    t = _URL.sub(ANON, t)
    t = _USER.sub(ANON, t)
    t = _PHONE.sub(ANON, t)
    t = _WS.sub(" ", t).strip()
    return t


def excerpt(text, n=200):
    t = anonymize(text)
    return (t[: n - 1] + "…") if len(t) > n else t


# ----------------------------------------------------------------------------
# THU THẬP (Reddit API, qua praw)
# ----------------------------------------------------------------------------
EXIT_BLOCKED = 4   # Reddit trả 403/429: dừng, không né (ranh giới dữ liệu số 4)


class BlockedError(Exception):
    """Nguồn chặn truy cập (403/429). Dừng cả lượt, không thử tiếp từ khóa khác."""


def _http_status(e):
    """Mã HTTP của một lỗi prawcore (nếu có), để nhận ra 401/403/429."""
    resp = getattr(e, "response", None)
    return getattr(resp, "status_code", None)


def fetch_reddit(days, limit_per_query):
    """Trả về list dict thô {id, subreddit, created_utc, title, body}.
    Không bao giờ đọc .author để tránh lưu định danh.
    403/429 từ Reddit -> BlockedError (dừng cả lượt). 401 -> thoát mã 1 (khóa sai)."""
    try:
        import praw  # import trễ: self-test không cần praw
        import prawcore
    except ImportError:
        sys.exit("Thiếu praw. Cài: pip install praw")

    cid = os.environ.get("REDDIT_CLIENT_ID")
    csec = os.environ.get("REDDIT_CLIENT_SECRET")
    ua = os.environ.get("REDDIT_USER_AGENT", "ihouzz-scan/0.1")
    if not (cid and csec):
        sys.exit("Thiếu REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET (tạo 'script app' tại "
                 "https://www.reddit.com/prefs/apps).")

    reddit = praw.Reddit(client_id=cid, client_secret=csec, user_agent=ua,
                         check_for_async=False)
    reddit.read_only = True

    cutoff = time.time() - days * 86400
    multi = reddit.subreddit("+".join(SUBREDDITS))
    seen, rows = set(), []
    for kw in KEYWORDS:
        try:
            for s in multi.search(kw, sort="new", time_filter="month",
                                  limit=limit_per_query):
                if s.id in seen or s.created_utc < cutoff:
                    continue
                seen.add(s.id)
                rows.append({
                    "id": s.id,
                    "subreddit": str(s.subreddit),
                    "created_utc": s.created_utc,
                    "title": s.title or "",
                    "body": getattr(s, "selftext", "") or "",
                    "matched_keyword": kw,
                })
        except prawcore.exceptions.PrawcoreException as e:
            status = _http_status(e)
            if status in (403, 429) or isinstance(e, prawcore.exceptions.Forbidden):
                # Bị chặn hoặc quá giới hạn: dừng NGAY, không thử từ khóa khác, không đổi cách gọi.
                raise BlockedError(f"Reddit trả HTTP {status or 403} khi tìm '{kw}'") from e
            if status == 401 or isinstance(e, prawcore.exceptions.OAuthException):
                sys.exit("Reddit từ chối khóa (401): kiểm tra REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET.")
            print(f"  ! lỗi khi tìm '{kw}': {e}", file=sys.stderr)  # lỗi khác: bỏ từ khóa này
        except Exception as e:  # một từ khóa lỗi (mạng, dữ liệu lạ) không làm hỏng cả lượt
            print(f"  ! lỗi khi tìm '{kw}': {e}", file=sys.stderr)
        time.sleep(1)  # lịch sự với API
    return rows


# ----------------------------------------------------------------------------
# PHÂN LOẠI (Claude). Thiếu key -> nhãn tạm để pipeline vẫn chạy.
# ----------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "Bạn phân loại bài đăng công khai (tiếng Việt/Anh) của cộng đồng người Việt "
    "liên quan Hàn Quốc, phục vụ thống kê nhu cầu ẩn danh. Chỉ trả về JSON."
)


def _classify_prompt(text):
    return (
        "Phân loại đoạn sau và CHỈ trả JSON với các khóa:\n"
        f"chu_de (một trong {CHU_DE}),\n"
        f"nhu_cau_ro (một trong {NHU_CAU}),\n"
        f"muc_cu_the (một trong {MUC_CU_THE}),\n"
        "dia_phuong_vn (tỉnh/vùng ở VN được nhắc, hoặc \"\"),\n"
        "noi_o_tai_han (nơi ở tại Hàn được nhắc, hoặc \"\"),\n"
        f"nhom_nguoi (một trong {NHOM_NGUOI}),\n"
        f"ngon_ngu (một trong {NGON_NGU}),\n"
        f"sac_thai (một trong {SAC_THAI}),\n"
        "la_quang_cao (true nếu là rao bán/môi giới/spam, nếu không false),\n"
        "trich_doan (tóm tắt đã diễn giải, <=200 ký tự, KHÔNG chép nguyên văn, "
        "KHÔNG chứa tên/sđt/link).\n\n"
        f"ĐOẠN:\n{text}"
    )


def classify(text):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return _stub_classify(text)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=DEFAULT_MODEL, max_tokens=500, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _classify_prompt(text)}],
        )
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        raw = raw[raw.find("{"): raw.rfind("}") + 1]
        data = json.loads(raw)
    except Exception as e:
        print(f"  ! phân loại lỗi, dùng nhãn tạm: {e}", file=sys.stderr)
        return _stub_classify(text)
    data["trich_doan"] = excerpt(data.get("trich_doan", "") or text)
    return data


_AD_WORDS = re.compile(r"(?<!\w)(bán|ib|inbox|liên hệ|giá tốt|sale)(?!\w)")


def _stub_classify(text):
    """Nhãn tạm bằng luật đơn giản (khi chưa có ANTHROPIC_API_KEY)."""
    low = anonymize(text).lower()
    chu_de = "Khác"
    if any(k in low for k in ["gửi tiền", "remit", "chuyển tiền", "tỷ giá"]):
        chu_de = "Tài chính và gửi tiền"
    elif any(k in low for k in ["đất", "nhà", "chung cư", "sổ đỏ", "bđs"]):
        chu_de = "Nhà đất tại VN"
    elif any(k in low for k in ["visa", "e-9", "eps", "việc", "job"]):
        chu_de = "Việc làm và visa"
    elif any(k in low for k in ["về nước", "định cư", "hồi hương"]):
        chu_de = "Về nước, định cư"
    # Khớp theo từ nguyên vẹn, để "ib" không bắt nhầm "possible", "describe"...
    is_ad = bool(_AD_WORDS.search(low))
    return {
        "chu_de": chu_de,
        "nhu_cau_ro": "Chỉ bàn luận",
        "muc_cu_the": "Hỏi chung",
        "dia_phuong_vn": "",
        "noi_o_tai_han": "",
        "nhom_nguoi": "Không rõ",
        "ngon_ngu": "Tiếng Việt",
        "sac_thai": "Trung tính",
        "la_quang_cao": is_ad,
        "trich_doan": excerpt(text),
        "_nhan_tam": True,
    }


# ----------------------------------------------------------------------------
# ĐẨY SANG LARK BASE (tùy chọn) — chỉ chạy khi có đủ biến môi trường
# ----------------------------------------------------------------------------
def push_to_lark(records):
    need = ["LARK_APP_ID", "LARK_APP_SECRET", "LARK_BASE_APP_TOKEN", "LARK_TABLE_ID"]
    if not all(os.environ.get(k) for k in need):
        print("  (bỏ qua Lark: chưa đặt " + ", ".join(need) + ")")
        return
    import requests
    dom = os.environ.get("LARK_DOMAIN", "https://open.larksuite.com")
    tok = requests.post(
        f"{dom}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": os.environ["LARK_APP_ID"],
              "app_secret": os.environ["LARK_APP_SECRET"]}, timeout=20
    ).json().get("tenant_access_token")
    if not tok:
        print("  ! không lấy được tenant_access_token", file=sys.stderr)
        return
    url = (f"{dom}/open-apis/bitable/v1/apps/{os.environ['LARK_BASE_APP_TOKEN']}"
           f"/tables/{os.environ['LARK_TABLE_ID']}/records/batch_create")
    fields = [{"fields": {
        "Tuần": r["tuan"], "Chủ đề chính": r["chu_de"], "Có nhu cầu rõ": r["nhu_cau_ro"],
        "Mức cụ thể": r["muc_cu_the"], "Địa phương VN": r["dia_phuong_vn"],
        "Nơi ở tại Hàn": r["noi_o_tai_han"], "Nhóm người đăng": r["nhom_nguoi"],
        "Ngôn ngữ": r["ngon_ngu"], "Sắc thái": r["sac_thai"],
        "Trích đoạn": r["trich_doan"], "Loại khỏi thống kê": bool(r["la_quang_cao"]),
        "Nguồn nhóm": f"Reddit · r/{r['subreddit']}", "Ngày đăng": r["ngay_dang"],
    }} for r in records]
    for i in range(0, len(fields), 100):  # Lark cho tối đa 100 record/lần
        resp = requests.post(url, headers={"Authorization": f"Bearer {tok}"},
                             json={"records": fields[i:i + 100]}, timeout=30).json()
        print(f"  Lark batch {i//100 + 1}: code={resp.get('code')}")


# ----------------------------------------------------------------------------
# CHẠY
# ----------------------------------------------------------------------------
def process_rows(raw, seen_hashes, classify_fn=None):
    """Làm sạch, ẩn danh, phân loại. Trả về (out, dropped, tam).

    seen_hashes được cập nhật TẠI CHỖ, nhưng chỉ với bài đã phân loại thật xong
    (kể cả bài quá ngắn hay quảng cáo đã xét). Bài mang nhãn tạm (_nhan_tam: thiếu
    khóa hoặc AI lỗi) KHÔNG được ghi "đã thấy", để lượt sau thử phân loại lại —
    trước đây bài này bị export_for_page.py --bo-nhan-tam loại rồi mất vĩnh viễn."""
    classify_fn = classify_fn or classify
    out, dropped, tam = [], 0, 0
    for r in raw:
        h = hashlib.sha1(r["id"].encode()).hexdigest()  # khử trùng không lưu id gốc
        if h in seen_hashes:
            continue
        text = anonymize((r["title"] + ". " + r["body"]).strip())
        if len(text) < 15:
            seen_hashes.add(h)  # bài rỗng: không cần xét lại
            continue
        cls = classify_fn(text)
        if cls.get("_nhan_tam"):
            tam += 1            # giữ trong file để xem, nhưng KHÔNG đánh dấu đã thấy
        else:
            seen_hashes.add(h)
        if cls.get("la_quang_cao"):
            dropped += 1
            continue  # loại quảng cáo khỏi thống kê nhu cầu
        out.append({
            "source": "reddit", "subreddit": r["subreddit"],
            "ngay_dang": _utc_day(r["created_utc"]), "tuan": _isoweek(r["created_utc"]),
            "matched_keyword": r["matched_keyword"], **{k: v for k, v in cls.items()},
        })
    return out, dropped, tam


def run(args):
    print(f"[1/4] Thu thập Reddit · {len(SUBREDDITS)} subreddit · {len(KEYWORDS)} từ khóa …")
    try:
        raw = fetch_reddit(args.days, args.limit)
    except BlockedError as e:
        # Ranh giới dữ liệu số 4: nguồn chặn thì dừng và báo, không dùng cách vòng.
        print(f"DỪNG: {e}. Không thử tiếp, không đổi cách gọi. Báo IT và chạy lại sau.",
              file=sys.stderr)
        sys.exit(EXIT_BLOCKED)
    print(f"      {len(raw)} bài thô.")

    print("[2/4] Làm sạch, ẩn danh & [3/4] phân loại …")
    seen_hashes = _load_seen(args.seen)
    out, dropped, tam = process_rows(raw, seen_hashes)

    print(f"      giữ {len(out)} tín hiệu · loại {dropped} quảng cáo.")
    if tam:
        print(f"      {tam} bài mang nhãn tạm (chưa đánh dấu đã thấy, lượt sau sẽ phân loại lại).")
    _write_jsonl(out, args.out)
    _save_seen(seen_hashes, args.seen)
    print(f"[4/4] Đã ghi {args.out}")
    if not args.no_lark:
        push_to_lark([r for r in out if not r.get("_nhan_tam")])  # Lark chỉ nhận nhãn thật


def _utc_day(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")


def _isoweek(ts):
    d = dt.datetime.fromtimestamp(ts, dt.timezone.utc).isocalendar()
    return f"{d[0]}-W{d[1]:02d}"


def _load_seen(path):
    try:
        with open(path, encoding="utf-8") as f:
            return set(x.strip() for x in f if x.strip())
    except FileNotFoundError:
        return set()


def _save_seen(s, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(s)))


def _write_jsonl(rows, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def self_test():
    """Kiểm tra ẩn danh + phân loại tạm, không cần mạng/khóa."""
    samples = [
        "Em ở Ansan 010-2957-4821, muốn gửi tiền về mua đất ở Nghệ An cho bố mẹ, "
        "ai biết chỗ xem giấy tờ uy tín ib em qua email a@b.com nhé https://x.co/y",
        "Bán đất nền quê giá tốt sổ đỏ chính chủ, liên hệ u/seller_123 ib ngay!",
    ]
    ok = True
    for s in samples:
        a = anonymize(s)
        assert "@" not in a and "http" not in a and "4821" not in a and "u/" not in a, a
        c = classify(a)
        print(json.dumps({"anon": a, "cls": c}, ensure_ascii=False, indent=2))

    # Nhãn tạm: "ib" chỉ bắt từ nguyên vẹn, không bắt "possible"/"describe".
    assert not _stub_classify("Is it possible to describe the EPS visa process?")["la_quang_cao"]
    assert _stub_classify("Có đất nền giá tốt, ib mình nhé")["la_quang_cao"]

    # Danh sách "đã thấy": chỉ ghi khi phân loại thật thành công.
    raw = [
        {"id": "a1", "subreddit": "korea", "created_utc": 1_760_000_000, "title": "Gửi tiền về",
         "body": "mua đất ở quê cho bố mẹ, ai có kinh nghiệm", "matched_keyword": "gửi tiền về"},
        {"id": "a2", "subreddit": "korea", "created_utc": 1_760_000_000, "title": "Về nước",
         "body": "định cư lại Đà Nẵng có khó không", "matched_keyword": "về nước"},
        {"id": "a3", "subreddit": "korea", "created_utc": 1_760_000_000, "title": "x",
         "body": "", "matched_keyword": "về nước"},
    ]
    real = {"chu_de": "Nhà đất tại VN", "nhu_cau_ro": "Có", "muc_cu_the": "Hỏi chung",
            "dia_phuong_vn": "", "noi_o_tai_han": "", "nhom_nguoi": "Lao động",
            "ngon_ngu": "Tiếng Việt", "sac_thai": "Trung tính", "la_quang_cao": False,
            "trich_doan": "Hỏi kinh nghiệm mua đất ở quê."}
    calls = {"n": 0}

    def fake_classify(text):  # bài 1 phân loại thật; bài 2 AI lỗi -> nhãn tạm
        calls["n"] += 1
        return dict(real) if calls["n"] == 1 else _stub_classify(text)

    seen = set()
    out, dropped, tam = process_rows(raw, seen, fake_classify)
    h = lambda i: hashlib.sha1(i.encode()).hexdigest()
    assert len(out) == 2 and tam == 1 and dropped == 0, (len(out), tam, dropped)
    assert h("a1") in seen, "bài phân loại thật phải được đánh dấu đã thấy"
    assert h("a2") not in seen, "bài nhãn tạm KHÔNG được đánh dấu đã thấy (để lượt sau thử lại)"
    assert h("a3") in seen, "bài rỗng được đánh dấu đã thấy"
    assert out[0]["ngay_dang"] == "2025-10-09" and out[0]["tuan"] == "2025-W41", out[0]
    # Lượt sau: bài 2 được xử lý lại, bài 1 và 3 bỏ qua.
    out2, _, tam2 = process_rows(raw, seen, lambda t: dict(real))
    assert len(out2) == 1 and tam2 == 0 and h("a2") in seen, (len(out2), tam2)
    assert "_nhan_tam" not in out2[0]

    print("\nself-test: OK — ẩn danh sạch, phân loại chạy, nhãn tạm không bị đánh dấu đã thấy, "
          "'ib' chỉ bắt từ nguyên vẹn." if ok else "FAIL")


def main():
    p = argparse.ArgumentParser(description="Quét tín hiệu Reddit (lớp 3) cho iHouzz.")
    p.add_argument("--days", type=int, default=7, help="Lấy bài trong N ngày gần nhất")
    p.add_argument("--limit", type=int, default=50, help="Số bài tối đa mỗi từ khóa")
    p.add_argument("--out", default="out/reddit_signals.jsonl")
    p.add_argument("--seen", default="out/seen_hashes.txt")
    p.add_argument("--no-lark", action="store_true", help="Chỉ ghi file, không đẩy Lark")
    p.add_argument("--self-test", action="store_true", help="Chạy thử offline")
    args = p.parse_args()
    if args.self_test:
        self_test()
    else:
        run(args)


if __name__ == "__main__":
    main()
