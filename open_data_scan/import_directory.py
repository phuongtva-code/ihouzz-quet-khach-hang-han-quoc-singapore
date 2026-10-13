#!/usr/bin/env python3
"""Nạp doanh nghiệp từ danh bạ công khai (file CSV) vào bảng "Dữ liệu AI quét" trên Lark Base.

Dùng cho Hàn Quốc và những nơi chưa có nguồn dữ liệu mở tự động. Người vận hành chuẩn bị file CSV
từ các danh bạ công khai (hội doanh nghiệp, hội đoàn Việt tự công bố danh sách, website riêng của
doanh nghiệp), bỏ vào thư mục `inbox/`. Script kiểm từng dòng, bỏ dòng sai luật, chống trùng, gắn
nhãn A/B/C rồi ghi vào Base. Dòng bị loại được ghi kèm lý do vào file `.rejected.csv`.

Luật cứng (kiểm tự động, không tắt được bằng cấu hình thường):
  - Chỉ doanh nghiệp, tổ chức. Không nạp người cá nhân.
  - Mỗi dòng phải có tên nguồn và đường link tới trang công khai chứa thông tin đó.
  - Link nguồn và website không được là mạng xã hội (Facebook, Zalo, LinkedIn, Instagram, TikTok...).
  - Điện thoại và email chỉ nhận khi cột `lien_he_do_doanh_nghiep_cong_bo` = co, tức chính doanh
    nghiệp hay tổ chức đã tự công bố. Email miễn phí (gmail, naver...) luôn bị bỏ vì có thể là của cá nhân.
  - Chỉ nhận khu vực trong danh sách cho phép; mỗi file tối đa `max_rows_per_file` dòng.

Chạy thử không cần khóa, không cần mạng:  python3 import_directory.py --self-test
Xem trước một file, không ghi:             python3 import_directory.py --file X.csv --dry-run
Chạy thật theo thư mục inbox:              python3 import_directory.py
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import shutil
import sys
from datetime import date, datetime

import scan_common as sc

HERE = os.path.dirname(os.path.abspath(__file__))

ALIASES = {
    "ten": ["ten", "ten_doanh_nghiep", "name"],
    "khu_vuc": ["khu_vuc", "region"],
    "nguon": ["nguon", "ten_nguon", "source"],
    "link_nguon": ["link_nguon", "link", "url", "nguon_link"],
    "ngay_quet": ["ngay_quet", "ngay", "date"],
    "dia_chi": ["dia_chi", "address"],
    "nganh": ["nganh", "industry"],
    "dien_thoai": ["dien_thoai", "dien_thoai_doanh_nghiep", "phone"],
    "website": ["website", "web"],
    "email": ["email", "email_doanh_nghiep"],
    "cong_bo": ["lien_he_do_doanh_nghiep_cong_bo", "cong_bo", "published_by_business"],
    "nhan": ["nhan", "label"],
    "ly_do": ["ly_do", "reason"],
}
REQUIRED = ["ten", "khu_vuc", "nguon", "link_nguon"]
_RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_RE_PHONE = re.compile(r"^[+()\d][\d\s().\-]{6,24}$")


def _header_key(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", sc.strip_accents(h or "").casefold()).strip("_")


def read_csv_text(text: str) -> list[dict]:
    """Đọc CSV, đưa tên cột về dạng chuẩn (không phân biệt dấu, hoa thường)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    alias_to_std = {a: std for std, names in ALIASES.items() for a in names}
    rows = []
    for raw in reader:
        row: dict = {}
        for k, v in raw.items():
            std = alias_to_std.get(_header_key(k or ""))
            if std and std not in row:
                row[std] = (v or "").strip()
        rows.append(row)
    return rows


def _banned(url: str, patterns: list[str]) -> bool:
    return any(re.search(p, url or "", re.I) for p in patterns)


def validate_row(row: dict, cfg: dict) -> tuple[dict | None, str, list[str]]:
    """Kiểm một dòng. Trả (dòng đã làm sạch hoặc None, lý do loại, các cảnh báo)."""
    d = cfg["directory_import"]
    warns: list[str] = []
    for f in REQUIRED:
        if not row.get(f):
            return None, f"thiếu cột bắt buộc: {f}", warns
    if row["khu_vuc"] not in d["allowed_regions"]:
        return None, f"khu vực '{row['khu_vuc']}' không nằm trong danh sách cho phép", warns
    link = row["link_nguon"]
    if not re.match(r"^https?://", link, re.I):
        return None, "link_nguon phải là đường link http(s) tới trang công khai", warns
    if _banned(link, d["banned_url_patterns"]):
        return None, ("link_nguon là mạng xã hội, ứng dụng nhắn tin hoặc Google Maps: không nạp ở đây "
                      "(tên/địa chỉ từ Google Maps không được lưu vào CSDL riêng)"), warns
    name = row["ten"]
    if "@" in name or re.search(r"\d{8,}", name):
        return None, "tên có vẻ là email hoặc số điện thoại, không phải tên doanh nghiệp", warns

    clean = dict(row)
    website = row.get("website", "")
    if website and (not re.match(r"^https?://", website, re.I) or _banned(website, d["banned_url_patterns"])):
        clean["website"] = ""
        warns.append("bỏ website (không phải website riêng của doanh nghiệp)")

    published = row.get("cong_bo", "").strip().casefold() in ("co", "có", "yes", "y", "true", "1")
    phone, email = row.get("dien_thoai", ""), row.get("email", "")
    if (phone or email) and not published:
        clean["dien_thoai"] = clean["email"] = ""
        warns.append("bỏ điện thoại/email vì cột lien_he_do_doanh_nghiep_cong_bo không phải 'co'")
    else:
        if phone and not _RE_PHONE.match(phone):
            clean["dien_thoai"] = ""
            warns.append("bỏ điện thoại không đúng dạng")
        if email:
            domain = email.rsplit("@", 1)[-1].casefold() if "@" in email else ""
            if not _RE_EMAIL.match(email):
                clean["email"] = ""
                warns.append("bỏ email không đúng dạng")
            elif domain in d["free_mail_domains"]:
                clean["email"] = ""
                warns.append("bỏ email miễn phí (có thể của cá nhân)")

    if row.get("ngay_quet"):
        try:
            datetime.strptime(row["ngay_quet"], "%Y-%m-%d")
        except ValueError:
            return None, "ngay_quet phải có dạng YYYY-MM-DD", warns
    if row.get("nhan") and row["nhan"].upper() not in ("A", "B", "C"):
        return None, "nhan chỉ được là A, B hoặc C", warns
    return clean, "", warns


def to_base_row(clean: dict, cfg: dict) -> dict:
    cols = cfg["columns"]
    has_contact = bool(clean.get("dien_thoai") or clean.get("website") or clean.get("email"))
    label, reason = sc.label_directory_row(clean["ten"], has_contact, cfg["viet_signals"])
    if clean.get("nhan"):
        label = clean["nhan"].upper()
    if clean.get("ly_do"):
        reason = clean["ly_do"][:300]
    ir = cfg["industry_rules"]
    industry = clean.get("nganh") or sc.industry_from_name(clean["ten"], ir["rules"], ir["default"])
    day = datetime.strptime(clean["ngay_quet"], "%Y-%m-%d").date() if clean.get("ngay_quet") else None
    return sc.build_row(
        cols, name=clean["ten"], region=clean["khu_vuc"], industry=industry,
        source=clean["nguon"], link=clean["link_nguon"], label=label, reason=reason,
        address=clean.get("dia_chi", ""), phone=clean.get("dien_thoai", ""),
        website=clean.get("website", ""), email=clean.get("email", ""), day=day,
    )


def process_rows(rows: list[dict], cfg: dict, existing: list[dict]) -> tuple[list[dict], list[dict]]:
    """Trả (các dòng ghi vào Base, các dòng bị loại kèm lý do)."""
    cols = cfg["columns"]
    seen = sc.existing_keys(existing, cols)
    accepted: list[dict] = []
    rejected: list[dict] = []
    for i, row in enumerate(rows, start=2):  # dòng 1 là tiêu đề
        clean, why, warns = validate_row(row, cfg)
        if clean is None:
            rejected.append({**row, "dong_trong_file": i, "ly_do_loai": why})
            continue
        keys = sc.dedupe_keys(clean["ten"], clean.get("dia_chi", ""), clean.get("dien_thoai", ""),
                              "", clean["khu_vuc"])
        if keys & seen:
            rejected.append({**row, "dong_trong_file": i, "ly_do_loai": "trùng với dòng đã có"})
            continue
        seen |= keys
        out = to_base_row(clean, cfg)
        accepted.append(out)
        if warns:
            accepted[-1]["__canh_bao"] = "; ".join(warns)  # chỉ để in log, bị bỏ trước khi ghi
    return accepted, rejected


def _strip_internal(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in r.items() if not k.startswith("__")} for r in rows]


def write_rejected(path: str, rejected: list[dict]) -> None:
    keys: list[str] = []
    for r in rejected:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rejected)


def import_file(path: str, cfg: dict, lark, existing: list[dict], write: bool, log) -> tuple[int, int, int]:
    """Nạp một file. Trả (số dòng ghi, số dòng loại, mã thoát)."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = read_csv_text(fh.read())
    limit = int(cfg["directory_import"].get("max_rows_per_file", 200))
    if len(rows) > limit:
        log.error("%s có %d dòng, vượt giới hạn %d. Hãy chia nhỏ file.", os.path.basename(path), len(rows), limit)
        return 0, len(rows), sc.EXIT_CONFIG
    accepted, rejected = process_rows(rows, cfg, existing)
    for r in accepted:
        if r.get("__canh_bao"):
            log.warning("%s: %s | %s", os.path.basename(path), r[cfg["columns"]["name"]], r["__canh_bao"])
    log.info("%s: %d dòng, nhận %d, loại %d.", os.path.basename(path), len(rows), len(accepted), len(rejected))
    out_rows = _strip_internal(accepted)
    if write and out_rows:
        try:
            lark.batch_create(out_rows)
        except sc.LarkError as exc:
            log.error("%s", exc)
            return exc.written, len(rejected), sc.EXIT_PARTIAL if exc.written else sc.EXIT_API
        existing.extend({k: str(v) for k, v in r.items()} for r in out_rows)
    if rejected and write:
        write_rejected(path[:-4] + ".rejected.csv", rejected)
    elif rejected:
        for r in rejected:
            log.info("Sẽ loại dòng %s (%s): %s", r["dong_trong_file"], r.get("ten", ""), r["ly_do_loai"])
    return len(out_rows), len(rejected), sc.EXIT_OK


def run_inbox(cfg: dict, lark, base_dir: str, write: bool, log) -> int:
    inbox = os.path.join(base_dir, cfg["directory_import"].get("inbox_dir", "inbox"))
    os.makedirs(os.path.join(inbox, "done"), exist_ok=True)
    files = sorted(f for f in os.listdir(inbox) if f.lower().endswith(".csv") and not f.lower().endswith(".rejected.csv"))
    if not files:
        log.info("Thư mục inbox trống: không có gì để nạp.")
        return sc.EXIT_OK
    existing = lark.list_all()
    total_in, worst = 0, sc.EXIT_OK
    stamp = datetime.now(sc.VN_TZ).strftime("%Y%m%d-%H%M")
    for f in files:
        path = os.path.join(inbox, f)
        n, rej, code = import_file(path, cfg, lark, existing, write, log)
        total_in += n
        if code != sc.EXIT_OK:
            worst = code
            log.error("Dừng ở %s; các file sau để lại trong inbox.", f)
            break
        if write:
            shutil.move(path, os.path.join(inbox, "done", f"{stamp}_{f}"))
            rj = path[:-4] + ".rejected.csv"
            if os.path.exists(rj):
                shutil.move(rj, os.path.join(inbox, "done", f"{stamp}_{os.path.basename(rj)}"))
    log.info("Đã thêm %d dòng mới từ danh bạ công khai.", total_in)
    return worst


# ---------------------------------------------------------------- Tự kiểm

def self_test() -> int:
    import json
    import logging
    import tempfile

    cfg = sc.load_config(os.path.join(HERE, "scan_config.json"))
    c = cfg["columns"]
    log = logging.getLogger("selftest_dir")
    log.addHandler(logging.NullHandler())
    log.setLevel(logging.CRITICAL)

    text = (
        "Tên,Khu vực,Nguồn,Link nguồn,Địa chỉ,Điện thoại,Website,Email,Liên hệ do doanh nghiệp công bố,Ngày quét\n"
        # 1: hợp lệ, doanh nghiệp tự công bố liên hệ, tên có từ khóa Việt Nam rõ ràng -> A
        "CÔNG TY THỬ NGHIỆM VIETNAM,Hàn Quốc,Danh bạ hội A (thử),https://example.org/danh-ba,Ansan,+82 31-000-0000,https://example.com,lienhe@example.com,co,2026-10-13\n"
        # 2: không cho phép liên hệ -> bỏ điện thoại và email, vẫn nhận
        "Cửa hàng Thử B,Hàn Quốc,Danh bạ hội A (thử),https://example.org/danh-ba,Suwon,+82 31-111-1111,,x@example.com,,\n"
        # 3: tên Hàn, không có dấu hiệu Việt -> C
        "베트남 아님 상점,Hàn Quốc,Danh bạ hội A (thử),https://example.org/danh-ba,Seoul,,,,,\n"
        # 4: link là Facebook -> loại
        "Quán Facebook,Hàn Quốc,Trang FB,https://www.facebook.com/profile.php?id=1,Seoul,,,,,\n"
        # 5: khu vực lạ -> loại
        "Cty X,Nhật Bản,Nguồn,https://example.org/x,Tokyo,,,,,\n"
        # 6: trùng dòng 1 (cùng tên + địa chỉ) -> loại
        "Công ty thử nghiệm Vietnam,Hàn Quốc,Danh bạ hội A (thử),https://example.org/danh-ba,ANSAN,,,,,\n"
        # 7: email miễn phí dù có công bố -> bỏ email
        "Hàng Việt Thử,Singapore,Danh bạ B (thử),https://example.org/b,Geylang,+65 6000 0000,,someone@gmail.com,co,\n"
        # 8: thiếu link nguồn -> loại
        "Cty Không Nguồn,Hàn Quốc,Nguồn,,Seoul,,,,,\n"
        # 9: website là Facebook -> bỏ website, vẫn nhận
        "Tiệm Y,Hàn Quốc,Danh bạ hội A (thử),https://example.org/danh-ba,Busan,,https://facebook.com/tiemy,,,\n"
        # 10: link nguồn là Google Maps -> loại (không lưu tên/địa chỉ từ Google Maps vào CSDL riêng)
        "Quán Google Maps,Hàn Quốc,Google Maps,https://www.google.com/maps/place/Quan+Viet/@37.3,126.7,17z,Ansan,,,,,\n"
        # 11: link rút gọn của Google Maps -> loại
        "Quán Goo.gl,Hàn Quốc,Google Maps,https://maps.app.goo.gl/AbCdEf123,Ansan,,,,,\n"
    )
    rows = read_csv_text(text)
    assert len(rows) == 11 and rows[0]["ten"].startswith("CÔNG TY"), rows[0]
    existing = [{c["name"]: "Dòng cũ", c["phone"]: "+65 6320 3880", c["region"]: "Singapore"}]
    accepted, rejected = process_rows(rows, cfg, existing)
    out = _strip_internal(accepted)
    names = [r[c["name"]] for r in out]
    assert names == ["CÔNG TY THỬ NGHIỆM VIETNAM", "Cửa hàng Thử B", "베트남 아님 상점", "Hàng Việt Thử", "Tiệm Y"], names
    r1, r2, r3, r4, r5 = out
    assert r1[c["label"]] == "A" and r1[c["phone"]] == "+82 31-000-0000" and r1[c["email"]] == "lienhe@example.com"
    assert r1[c["scan_date"]] == 1791867600000
    assert c["phone"] not in r2 and c["email"] not in r2, "chưa được công bố thì không nạp liên hệ"
    assert r3[c["label"]] == "C"
    assert c["email"] not in r4 and r4[c["phone"]] == "+65 6000 0000", "email miễn phí phải bị bỏ"
    assert c["website"] not in r5, "website Facebook phải bị bỏ"
    reasons = {r["ten"]: r["ly_do_loai"] for r in rejected}
    assert "mạng xã hội" in reasons["Quán Facebook"]
    assert "Google Maps" in reasons["Quán Google Maps"] and "Google Maps" in reasons["Quán Goo.gl"], reasons
    assert not _banned("https://example.org/google-maps-huong-dan", cfg["directory_import"]["banned_url_patterns"])
    assert "không nằm trong danh sách" in reasons["Cty X"]
    assert "trùng" in reasons["Công ty thử nghiệm Vietnam"]
    assert "link_nguon" in reasons["Cty Không Nguồn"]
    for r in out:
        for tuy_khach in ("Quy mô", "Trạng thái duyệt", "Nhận xét TGĐ"):
            assert tuy_khach not in r

    # Nạp thật bằng Lark giả lập, kiểm tra luồng inbox: file chuyển sang done/, có file .rejected.csv
    sent: list = []

    def transport(method, url, headers, body, timeout):
        if url.endswith("/tenant_access_token/internal"):
            return 200, {"code": 0, "tenant_access_token": "t", "expire": 7200}
        if method == "GET":
            return 200, {"code": 0, "data": {"has_more": False, "items": []}}
        sent.extend(body["records"])
        return 200, {"code": 0, "data": {}}

    lark = sc.LarkBase("a", "b", "APP", "TBL", transport=transport, sleep=lambda s: None)
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "inbox"))
        with open(os.path.join(tmp, "inbox", "thu.csv"), "w", encoding="utf-8") as fh:
            fh.write(text)
        code = run_inbox(cfg, lark, tmp, True, log)
        assert code == sc.EXIT_OK, code
        done = os.listdir(os.path.join(tmp, "inbox", "done"))
        assert any(f.endswith("_thu.csv") for f in done) and any(f.endswith(".rejected.csv") for f in done), done
        assert not os.path.exists(os.path.join(tmp, "inbox", "thu.csv"))
        assert len(sent) == 5, len(sent)
        # file quá dài bị từ chối cả file
        big_cfg = json.loads(json.dumps(cfg))
        big_cfg["directory_import"]["max_rows_per_file"] = 3
        with open(os.path.join(tmp, "inbox", "dai.csv"), "w", encoding="utf-8") as fh:
            fh.write(text)
        sent.clear()
        code = run_inbox(big_cfg, lark, tmp, True, log)
        assert code == sc.EXIT_CONFIG and not sent, (code, sent)
        assert os.path.exists(os.path.join(tmp, "inbox", "dai.csv")), "file lỗi phải ở lại inbox"

    print("self-test: OK (đọc CSV có dấu, chặn mạng xã hội và Google Maps, bỏ liên hệ chưa được công bố, "
          "bỏ email miễn phí, bỏ website Facebook, chống trùng, nhãn A/C, luồng inbox, file quá dài)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.path.join(HERE, "scan_config.json"))
    ap.add_argument("--file", help="Chỉ xử lý một file CSV (không chuyển file sau khi nạp)")
    ap.add_argument("--dry-run", action="store_true", help="Kiểm và in kết quả, không ghi vào Base")
    ap.add_argument("--log-dir", default=os.path.join(HERE, "logs"))
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()

    log = sc.setup_logging(args.log_dir, "import_directory")
    try:
        cfg = sc.load_config(args.config)
        lark = sc.make_lark(cfg)
        if args.file:
            existing = lark.list_all()
            n, rej, code = import_file(args.file, cfg, lark, existing, not args.dry_run, log)
            log.info("Đã thêm %d dòng, loại %d.", n if not args.dry_run else 0, rej)
            return code
        return run_inbox(cfg, lark, HERE, not args.dry_run, log)
    except sc.BlockedError as exc:
        log.error("%s", exc)
        return sc.EXIT_BLOCKED
    except sc.LarkError as exc:
        log.error("Lark lỗi: %s", exc)
        return sc.EXIT_API
    except sc.ScanError as exc:
        log.error("%s", exc)
        return sc.EXIT_CONFIG if "biến môi trường" in str(exc) else sc.EXIT_API
    except (OSError, KeyError, ValueError) as exc:
        log.error("Lỗi cấu hình hoặc file: %s", exc)
        return sc.EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
