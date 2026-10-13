#!/usr/bin/env python3
"""Quét doanh nghiệp liên quan Việt Nam ở Singapore từ dữ liệu mở ACRA (data.gov.sg).

Mỗi lần chạy:
  1. Đọc bảng "Dữ liệu AI quét" trên Lark Base để biết đã có gì (chống trùng theo UEN, tên + địa chỉ).
  2. Tìm trong bộ "Entities Registered with ACRA" theo các từ khóa Việt Nam trong tên doanh nghiệp.
  3. Giữ doanh nghiệp đang hoạt động, loại hộ kinh doanh cá thể (mặc định), bỏ dòng trùng.
  4. Ghi tối đa N dòng mới (mặc định 60), ưu tiên tên có từ khóa Việt Nam rõ ràng rồi đến doanh nghiệp mới lập.

Chỉ dùng dữ liệu công khai theo Singapore Open Data Licence. Không có điện thoại, website: bộ dữ liệu
không có các cột đó và script không tìm ở đâu khác. Gặp 403 hoặc 429 thì dừng và báo, không né.

Chạy thử không cần khóa, không cần mạng:   python3 sg_acra_scan.py --self-test
Chạy thử có đọc dữ liệu thật, không ghi:   python3 sg_acra_scan.py --dry-run
Chạy thật:                                 python3 sg_acra_scan.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from datetime import date

import scan_common as sc

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- Lấy dữ liệu từ ACRA

def fetch_keyword(cfg: dict, keyword: str, transport, sleep, log) -> list[dict]:
    """Lấy mọi bản ghi khớp một từ khóa (phân trang theo offset, có giới hạn số trang)."""
    sg = cfg["sg_acra"]
    headers = {}
    api_key = os.environ.get("DATA_GOV_SG_API_KEY", "").strip()
    if api_key:
        headers[sg.get("api_key_header", "x-api-key")] = api_key
    out: list[dict] = []
    offset = 0
    for _ in range(int(sg["max_pages_per_keyword"])):
        url = (
            f'{sg["api_url"]}?resource_id={sg["dataset_id"]}'
            f'&q={urllib.parse.quote(keyword)}&limit={int(sg["page_size"])}&offset={offset}'
        )
        js = sc.http_call(transport, "GET", url, headers, None, retries_429=1, wait_429=30.0, sleep=sleep)
        if not isinstance(js, dict) or not js.get("success"):
            raise sc.ScanError(f"data.gov.sg trả về dạng lạ cho từ khóa '{keyword}': {str(js)[:200]}")
        result = js.get("result") or {}
        recs = result.get("records") or []
        out.extend(recs)
        offset += len(recs)
        total = int(result.get("total") or 0)
        if not recs or offset >= total:
            break
        sleep(float(sg.get("sleep_between_calls_sec", 1.0)))
    log.info("Từ khóa %-14s: %d bản ghi", keyword, len(out))
    return out


# ---------------------------------------------------------------- Lọc và dựng dòng

def build_candidates(records: list[dict], cfg: dict) -> tuple[list[dict], dict]:
    """Lọc bản ghi ACRA thành danh sách ứng viên (đã sắp ưu tiên). Trả (ứng viên, thống kê bỏ qua)."""
    sg = cfg["sg_acra"]
    skipped = {"khong_hoat_dong": 0, "ca_the": 0, "khong_co_tu_khoa_trong_ten": 0, "trung_trong_lan_chay": 0}
    markers = [m.casefold() for m in sg.get("sole_proprietorship_markers", [])]
    seen_uen: set[str] = set()
    out: list[dict] = []
    for rec in records:
        uen = (rec.get("uen") or "").strip().upper()
        name = (rec.get("entity_name") or "").strip()
        if not uen or not name:
            continue
        if uen in seen_uen:
            skipped["trung_trong_lan_chay"] += 1
            continue
        seen_uen.add(uen)
        if (rec.get("uen_status_desc") or "").strip() not in sg["status_include"]:
            skipped["khong_hoat_dong"] += 1
            continue
        etype = (rec.get("entity_type_desc") or "").strip()
        if not sg.get("include_sole_proprietorship") and any(m in etype.casefold() for m in markers):
            skipped["ca_the"] += 1
            continue
        sig = sc.viet_signal(name, cfg["viet_signals"])
        if not sig:
            skipped["khong_co_tu_khoa_trong_ten"] += 1
            continue
        street = (rec.get("reg_street_name") or "").strip().title()
        postal = (rec.get("reg_postal_code") or "").strip()
        address = ", ".join(p for p in (street, f"Singapore {postal}".strip()) if p)
        out.append({
            "uen": uen, "name": name, "etype": etype, "issued": (rec.get("uen_issue_date") or "").strip(),
            "address": address, "signal": sig,
        })
    # Từ khóa rõ ràng trước, rồi doanh nghiệp lập gần đây trước, rồi theo UEN cho ổn định.
    out.sort(key=lambda c: (0 if c["signal"] == "strong" else 1, _neg_date(c["issued"]), c["uen"]))
    return out, skipped


def _neg_date(iso: str) -> str:
    """Khóa sắp xếp giảm dần theo ngày dạng YYYY-MM-DD (ngày trống xếp cuối)."""
    if not iso:
        return "9"
    return "".join(chr(ord("9") - ord(ch) + ord("0")) if ch.isdigit() else ch for ch in iso)


def candidate_link(cfg: dict, uen: str) -> str:
    sg = cfg["sg_acra"]
    return f'{sg["api_url"]}?resource_id={sg["dataset_id"]}&q={uen}'


def candidate_to_row(cfg: dict, cand: dict, day: date | None = None) -> dict:
    cols = cfg["columns"]
    if cand["signal"] == "strong":
        label = "A"
        why = "Tên công ty có từ khóa Việt Nam rõ ràng"
    else:
        label = "B"
        why = "Tên công ty chỉ có từ khóa yếu về Việt Nam"
    reason = (
        f"Nguồn đăng ký doanh nghiệp ACRA: {why}, đang hoạt động. "
        f"UEN {cand['uen']}, {cand['etype']}, cấp {cand['issued'] or 'không rõ ngày'}. "
        "Chưa có điện thoại hay website; chưa xác nhận chủ là người Việt."
    )
    return sc.build_row(
        cols,
        name=cand["name"], region="Singapore",
        industry=sc.industry_from_name(cand["name"], cfg["industry_rules"]["rules"], cfg["industry_rules"]["default"]),
        source=cfg["sg_acra"]["source_label"], link=candidate_link(cfg, cand["uen"]),
        label=label, reason=reason, address=cand["address"], day=day,
    )


def pick_new_rows(cfg: dict, candidates: list[dict], existing: list[dict], max_new: int,
                  day: date | None = None) -> tuple[list[dict], int]:
    """Chọn tối đa max_new dòng chưa có trong Base. Trả (dòng mới, số ứng viên trùng với Base)."""
    cols = cfg["columns"]
    seen = sc.existing_keys(existing, cols)
    rows: list[dict] = []
    dup = 0
    for cand in candidates:
        keys = sc.dedupe_keys(cand["name"], cand["address"], "", candidate_link(cfg, cand["uen"]))
        if keys & seen:
            dup += 1
            continue
        if len(rows) >= max_new:
            continue
        seen |= keys
        rows.append(candidate_to_row(cfg, cand, day))
    return rows, dup


# ---------------------------------------------------------------- Chạy

def run(cfg: dict, *, lark, transport, max_new: int, write: bool, log, sleep=time.sleep,
        day: date | None = None) -> int:
    cols = cfg["columns"]
    existing = lark.list_all() if lark is not None else []
    if lark is None:
        log.info("Chế độ không đọc Base: không chống trùng, chỉ để thử nguồn.")
    else:
        log.info("Bảng hiện có %d dòng.", len(existing))

    records: list[dict] = []
    for kw in cfg["sg_acra"]["search_keywords"]:
        records.extend(fetch_keyword(cfg, kw, transport, sleep, log))
        sleep(float(cfg["sg_acra"].get("sleep_between_calls_sec", 1.0)))

    candidates, skipped = build_candidates(records, cfg)
    rows, dup = pick_new_rows(cfg, candidates, existing, max_new, day)
    backlog = len(candidates) - dup - len(rows)
    n_a = sum(1 for r in rows if r.get(cols["label"]) == "A")
    n_b = sum(1 for r in rows if r.get(cols["label"]) == "B")
    log.info(
        "Ứng viên hợp lệ %d; đã có trong Base %d; chọn ghi %d (A %d, B %d); còn chờ tuần sau %d. Bỏ qua: %s",
        len(candidates), dup, len(rows), n_a, n_b, max(backlog, 0), json.dumps(skipped, ensure_ascii=False),
    )

    if not write:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))
        log.info("Chế độ không ghi: không có gì được ghi vào Base.")
        return sc.EXIT_OK
    if not rows:
        log.info("Đã thêm 0 dòng mới: Singapore 0.")
        return sc.EXIT_OK
    try:
        written = lark.batch_create(rows)
    except sc.LarkError as exc:
        log.error("%s", exc)
        return sc.EXIT_PARTIAL if exc.written else sc.EXIT_API
    log.info("Đã thêm %d dòng mới: Singapore %d.", written, written)
    return sc.EXIT_OK


# ---------------------------------------------------------------- Tự kiểm (không cần mạng, không cần khóa)

def self_test() -> int:
    import copy
    import logging
    from datetime import date as _date

    cfg = sc.load_config(os.path.join(HERE, "scan_config.json"))
    cfg = copy.deepcopy(cfg)
    cfg["sg_acra"]["page_size"] = 2
    cfg["sg_acra"]["search_keywords"] = ["vietnam", "viet"]
    log = logging.getLogger("selftest")
    log.addHandler(logging.NullHandler())
    log.setLevel(logging.CRITICAL)

    def rec(uen, name, status="Registered", etype="Local Company", issued="2021-05-04", street="RAFFLES PLACE", postal="048616"):
        return {"uen": uen, "entity_name": name, "uen_status_desc": status, "entity_type_desc": etype,
                "uen_issue_date": issued, "reg_street_name": street, "reg_postal_code": postal,
                "issuance_agency_desc": "ACRA"}

    acra = {
        "vietnam": [
            rec("202100001A", "VIETNAM FOOD SUPPLIER PTE. LTD.", street="UPPER PAYA LEBAR ROAD", postal="534963"),
            rec("202100002B", "OLD VIETNAM TRADING PTE. LTD.", status="Deregistered"),
            rec("202100003C", "SAIGON KITCHEN PTE. LTD.", issued="2024-02-01"),
        ],
        "viet": [
            rec("202100003C", "SAIGON KITCHEN PTE. LTD."),                      # trùng trong lần chạy
            rec("T21LL0004A", "PHO VIET", etype="Sole Proprietorship/ Partnership"),  # cá thể: loại
            rec("202100005D", "VIET CHEF PTE. LTD.", issued="2023-07-07"),        # từ khóa yếu -> B
            rec("202100006E", "ALREADY IN BASE PTE. LTD. VIETNAM"),               # đã có trong Base theo UEN
            rec("202100007F", "SOME OTHER COMPANY PTE. LTD."),                    # không có từ khóa trong tên
        ],
    }
    base_rows = [{
        cfg["columns"]["name"]: "Công ty đã có",
        cfg["columns"]["link"]: [{"type": "url", "text": candidate_link(cfg, "202100006E"),
                                   "link": candidate_link(cfg, "202100006E")}],
    }]
    # Dòng cũ lấy từ Google Maps (có điện thoại, địa chỉ) không được làm hỏng khóa chống trùng
    base_rows.append({
        cfg["columns"]["name"]: "Ky Anh Quan", cfg["columns"]["phone"]: "+65 6320 3880",
        cfg["columns"]["link"]: "https://www.google.com/maps/place/?q=place_id:ChIJa-blPxIY2jERcmM_gyd5BiQ",
    })

    captured: dict = {"batches": [], "acra_calls": 0, "lark_list_calls": 0}

    def transport(method, url, headers, body, timeout):
        if url.endswith("/auth/v3/tenant_access_token/internal"):
            assert body == {"app_id": "id", "app_secret": "secret"}
            return 200, {"code": 0, "tenant_access_token": "t-123", "expire": 7200}
        if "/bitable/v1/apps/" in url and method == "GET":
            assert headers.get("Authorization") == "Bearer t-123", headers
            captured["lark_list_calls"] += 1
            if "page_token=P2" in url:
                return 200, {"code": 0, "data": {"has_more": False, "items": [{"fields": base_rows[1]}]}}
            return 200, {"code": 0, "data": {"has_more": True, "page_token": "P2",
                                              "items": [{"fields": base_rows[0]}]}}
        if url.endswith("/records/batch_create"):
            captured["batches"].append(body)
            return 200, {"code": 0, "data": {"records": [{}] * len(body["records"])}}
        if "datastore_search" in url:
            captured["acra_calls"] += 1
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            kw, off, lim = q["q"][0], int(q["offset"][0]), int(q["limit"][0])
            data = acra.get(kw, [])
            return 200, {"success": True, "result": {"records": data[off:off + lim], "total": len(data)}}
        raise AssertionError("URL không mong đợi: " + url)

    lark = sc.LarkBase("id", "secret", "APP", "TBL", transport=transport, sleep=lambda s: None)
    day = _date(2026, 10, 13)
    code = run(cfg, lark=lark, transport=transport, max_new=60, write=True, log=log, sleep=lambda s: None, day=day)
    assert code == sc.EXIT_OK, code
    assert captured["lark_list_calls"] == 2, "phải đọc đủ 2 trang của Lark"
    assert captured["acra_calls"] >= 3, "phải phân trang ACRA"
    assert len(captured["batches"]) == 1
    rows = [r["fields"] for r in captured["batches"][0]["records"]]
    names = [r[cfg["columns"]["name"]] for r in rows]
    # Ưu tiên: rõ ràng trước (mới trước), yếu sau
    assert names == ["SAIGON KITCHEN PTE. LTD.", "VIETNAM FOOD SUPPLIER PTE. LTD.", "VIET CHEF PTE. LTD."], names
    c = cfg["columns"]
    first = rows[0]
    assert first[c["region"]] == "Singapore" and first[c["label"]] == "A"
    assert first[c["scan_date"]] == 1791867600000, first[c["scan_date"]]  # 12:00 giờ VN, 13/10/2026
    assert first[c["source"]].startswith("ACRA") and "q=202100003C" in first[c["link"]]
    assert first[c["industry"]] == "Ăn uống (theo tên)", first[c["industry"]]
    assert rows[1][c["industry"]] == "Thương mại, xuất nhập khẩu (theo tên)", rows[1][c["industry"]]
    assert rows[1][c["address"]] == "Upper Paya Lebar Road, Singapore 534963", rows[1][c["address"]]
    assert rows[2][c["label"]] == "B"
    for r in rows:
        assert c["phone"] not in r and c["website"] not in r and c["email"] not in r
        for tuy_khach in ("Quy mô", "Trạng thái duyệt", "Nhận xét TGĐ"):
            assert tuy_khach not in r, "không được ghi cột của TGĐ"
        assert "chưa xác nhận chủ" in r[c["reason"]].casefold()

    # Giới hạn số dòng mới
    captured["batches"].clear()
    run(cfg, lark=lark, transport=transport, max_new=1, write=True, log=log, sleep=lambda s: None, day=day)
    assert len(captured["batches"][0]["records"]) == 1

    # Chế độ không ghi
    import contextlib
    import io
    captured["batches"].clear()
    with contextlib.redirect_stdout(io.StringIO()):
        run(cfg, lark=lark, transport=transport, max_new=60, write=False, log=log, sleep=lambda s: None, day=day)
    assert captured["batches"] == []

    # Bật hộ kinh doanh cá thể: PHO VIET (từ khóa yếu) phải xuất hiện
    cfg2 = copy.deepcopy(cfg)
    cfg2["sg_acra"]["include_sole_proprietorship"] = True
    cands, _ = build_candidates(sum(acra.values(), []), cfg2)
    assert "PHO VIET" in [x["name"] for x in cands]

    # 403 phải dừng ngay, không thử lại
    calls = {"n": 0}

    def blocked(method, url, headers, body, timeout):
        calls["n"] += 1
        return 403, "forbidden"
    try:
        sc.http_call(blocked, "GET", "https://example.invalid/x", sleep=lambda s: None)
        raise AssertionError("phải ném BlockedError")
    except sc.BlockedError:
        assert calls["n"] == 1

    # 429: chờ một lần rồi vẫn 429 thì dừng
    calls["n"] = 0

    def limited(method, url, headers, body, timeout):
        calls["n"] += 1
        return 429, "slow down"
    try:
        sc.http_call(limited, "GET", "https://example.invalid/x", retries_429=1, sleep=lambda s: None)
        raise AssertionError("phải ném BlockedError")
    except sc.BlockedError:
        assert calls["n"] == 2

    # Lark lỗi giữa chừng: báo số dòng đã ghi
    def flaky(method, url, headers, body, timeout):
        if url.endswith("/tenant_access_token/internal"):
            return 200, {"code": 0, "tenant_access_token": "t", "expire": 7200}
        flaky.n += 1
        if flaky.n == 1:
            return 200, {"code": 0, "data": {}}
        return 200, {"code": 1254045, "msg": "FieldNameNotFound"}
    flaky.n = 0
    lk = sc.LarkBase("a", "b", "A", "T", transport=flaky, sleep=lambda s: None)
    try:
        lk.batch_create([{"x": 1}] * 150, chunk=100)
        raise AssertionError("phải ném LarkError")
    except sc.LarkError as exc:
        assert exc.written == 100, exc.written

    # Lark trả HTTP 400 ở lô 2 (không phải code != 0): vẫn phải báo đã ghi 100 dòng
    def flaky_http(method, url, headers, body, timeout):
        if url.endswith("/tenant_access_token/internal"):
            return 200, {"code": 0, "tenant_access_token": "t", "expire": 7200}
        flaky_http.n += 1
        if flaky_http.n == 1:
            return 200, {"code": 0, "data": {}}
        return 400, {"code": 99991663, "msg": "invalid request"}
    flaky_http.n = 0
    lk = sc.LarkBase("a", "b", "A", "T", transport=flaky_http, sleep=lambda s: None)
    try:
        lk.batch_create([{"x": 1}] * 150, chunk=100)
        raise AssertionError("phải ném LarkError")
    except sc.LarkError as exc:
        assert exc.written == 100, exc.written

    # Lark trả 403 (app chưa được thêm vào Base): là lỗi Lark (mã 4), KHÔNG phải "nguồn chặn" (mã 2)
    def lark_forbidden(method, url, headers, body, timeout):
        if url.endswith("/tenant_access_token/internal"):
            return 200, {"code": 0, "tenant_access_token": "t", "expire": 7200}
        return 403, {"code": 91403, "msg": "Forbidden"}
    lk = sc.LarkBase("a", "b", "A", "T", transport=lark_forbidden, sleep=lambda s: None)
    try:
        lk.list_all()
        raise AssertionError("phải ném LarkError")
    except sc.BlockedError:
        raise AssertionError("403 của Lark không được coi là nguồn chặn")
    except sc.LarkError as exc:
        assert "quyền" in str(exc), exc

    # Lark trả HTML (không phải JSON) với HTTP 200: báo lỗi rõ thay vì AttributeError
    def lark_html(method, url, headers, body, timeout):
        if url.endswith("/tenant_access_token/internal"):
            return 200, {"code": 0, "tenant_access_token": "t", "expire": 7200}
        return 200, "<html>maintenance</html>"
    lk = sc.LarkBase("a", "b", "A", "T", transport=lark_html, sleep=lambda s: None)
    try:
        lk.list_all()
        raise AssertionError("phải ném LarkError")
    except sc.LarkError as exc:
        assert "JSON" in str(exc), exc

    # Kết nối bị ngắt giữa chừng là lỗi mạng (ScanError), không phải lỗi cấu hình/file (OSError)
    import urllib.request as _ur
    _real_open = _ur.urlopen

    def _reset(*a, **k):
        raise ConnectionResetError(104, "Connection reset by peer")
    _ur.urlopen = _reset
    try:
        sc.default_transport("GET", "https://example.invalid/x", {}, None, 5)
        raise AssertionError("phải ném ScanError")
    except sc.ScanError as exc:
        assert "Lỗi mạng" in str(exc), exc
    except OSError:
        raise AssertionError("ConnectionResetError phải được bọc thành ScanError")
    finally:
        _ur.urlopen = _real_open

    print("self-test: OK (đọc 2 trang Lark, phân trang ACRA, chống trùng theo UEN và tên+địa chỉ, "
          "loại cá thể và không hoạt động, nhãn A/B, giới hạn dòng, chế độ không ghi, 403/429, "
          "lỗi ghi giữa chừng kể cả HTTP 4xx, 403 của Lark là lỗi quyền, Lark trả không phải JSON, lỗi mạng)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.path.join(HERE, "scan_config.json"))
    ap.add_argument("--max-new", type=int, default=None, help="Số dòng mới tối đa (mặc định theo scan_config.json)")
    ap.add_argument("--dry-run", action="store_true", help="Đọc Base và ACRA thật nhưng không ghi gì")
    ap.add_argument("--no-base", action="store_true", help="Không đụng tới Lark (không chống trùng); chỉ để thử nguồn")
    ap.add_argument("--log-dir", default=os.path.join(HERE, "logs"))
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    log = sc.setup_logging(args.log_dir, "sg_acra_scan")
    try:
        cfg = sc.load_config(args.config)
        max_new = args.max_new if args.max_new is not None else int(cfg["limits"]["max_new_rows_per_run"])
        lark = None if args.no_base else sc.make_lark(cfg)
        return run(cfg, lark=lark, transport=sc.default_transport, max_new=max_new,
                   write=not (args.dry_run or args.no_base), log=log)
    except sc.BlockedError as exc:
        log.error("Nguồn chặn hoặc giới hạn tốc độ, DỪNG và báo lại (không né): %s", exc)
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
