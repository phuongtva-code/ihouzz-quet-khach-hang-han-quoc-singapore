#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kosis_ingest.py — Lấy số người Việt theo tỉnh/thành từ KOSIS OpenAPI (Cục Thống kê
Hàn Quốc) và xuất các dòng kind="stat" theo IMPORT_SPEC.md.

Dùng API chính thức của KOSIS với khóa của iHouzz. Không cào trang web.

QUAN TRỌNG — mã bảng KOSIS KHÔNG được điền sẵn:
  orgId, tblId, itmId, objL1..8, prdSe nằm trong kosis_config.json và đang để TRỐNG.
  Người phát triển không biết chắc mã của bảng "người nước ngoài theo quốc tịch x tỉnh"
  nên không đoán. IT phải điền (hướng dẫn trong kosis_config.json và INSTALL_IT.md).
  Còn trống hoặc thiếu KOSIS_API_KEY thì script DỪNG (mã thoát 2) và nói rõ còn thiếu gì.

Dùng:
    export KOSIS_API_KEY=...
    python3 kosis_ingest.py                    # ghi out/kosis_stats.jsonl
    python3 kosis_ingest.py --dry-run          # gọi KOSIS thật, in thử, không ghi file
    python3 kosis_ingest.py --self-test        # thử logic offline bằng dữ liệu GIẢ LẬP

Mã thoát: 0 = xong; 2 = chưa cấu hình (thiếu khóa/mã bảng) — chuỗi chạy hằng ngày coi là
          "bỏ qua"; 3 = lỗi (file cấu hình hỏng, gọi KOSIS lỗi, hoặc dữ liệu không khớp).
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DEFAULT_CONFIG = os.path.join(HERE, "kosis_config.json")
DEFAULT_API_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
METRIC = "nguoi_viet_theo_tinh"
EXIT_NOT_READY, EXIT_KOSIS = 2, 3

# Tên tỉnh/thành (tiếng Hàn) -> tên dùng trong IMPORT_SPEC.md.
# Chuẩn hóa trước khi tra: bỏ khoảng trắng, dấu ngoặc, dấu chấm giữa.
PROVINCE_MAP = {
    "전국": "Toàn quốc",
    "서울특별시": "Seoul", "서울": "Seoul",
    "부산광역시": "Busan", "부산": "Busan",
    "인천광역시": "Incheon", "인천": "Incheon",
    "대구광역시": "Daegu", "대구": "Daegu",
    "대전광역시": "Daejeon", "대전": "Daejeon",
    "광주광역시": "Gwangju", "광주": "Gwangju",
    "울산광역시": "Ulsan", "울산": "Ulsan",
    "세종특별자치시": "Sejong", "세종": "Sejong",
    "경기도": "Gyeonggi", "경기": "Gyeonggi",
    "강원도": "Gangwon", "강원특별자치도": "Gangwon", "강원": "Gangwon",
    "충청북도": "Chungcheong Bắc", "충북": "Chungcheong Bắc",
    "충청남도": "Chungcheong Nam", "충남": "Chungcheong Nam",
    "전라북도": "Jeolla Bắc", "전북특별자치도": "Jeolla Bắc", "전북": "Jeolla Bắc",
    "전라남도": "Jeolla Nam", "전남": "Jeolla Nam",
    "경상북도": "Gyeongsang Bắc", "경북": "Gyeongsang Bắc",
    "경상남도": "Gyeongsang Nam", "경남": "Gyeongsang Nam",
    "제주특별자치도": "Jeju", "제주도": "Jeju", "제주": "Jeju",
}

# Gợi ý nhận chiều theo TÊN chiều (C<n>_OBJ_NM). Lưu ý "국적(지역)별" chứa chữ 지역
# nên KHÔNG dùng "지역" làm gợi ý cho tỉnh/thành.
HINT_NATIONALITY = ("국적",)
HINT_SEX = ("성별",)
HINT_PROVINCE = ("행정구역", "시도", "시ㆍ도", "시·도")

OK_UNITS = ("", "명", "인")
MAX_AXES = 8


class KosisError(Exception):
    """Lỗi có thể giải thích cho người vận hành (nội dung tiếng Việt)."""


# ----------------------------------------------------------------------------
# TIỆN ÍCH
# ----------------------------------------------------------------------------
def _norm(s):
    s = unicodedata.normalize("NFC", str(s if s is not None else ""))
    return re.sub(r"[\s()（）ㆍ·]", "", s)


def _mask(text, key):
    """Che khóa API khỏi mọi thông báo/log (thông báo lỗi của requests có chứa cả URL)."""
    text = str(text)
    if key:
        text = text.replace(key, "***")
    return re.sub(r"(apiKey=)[^&\s]+", r"\1***", text, flags=re.I)


def load_config(path):
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        raise KosisError(f"Không thấy file cấu hình {path}")
    except ValueError as e:
        raise KosisError(f"File cấu hình {path} sai cú pháp JSON: {e}")
    if not isinstance(cfg, dict):
        raise KosisError(f"File cấu hình {path} phải là một đối tượng JSON {{...}}")
    return cfg


def _s(cfg, k):
    v = cfg.get(k, "")
    return str(v).strip() if v is not None else ""


def check_ready(cfg, key):
    """Danh sách những gì còn thiếu (rỗng = sẵn sàng)."""
    missing = []
    if not key:
        missing.append("biến môi trường KOSIS_API_KEY (xin khóa tại https://kosis.kr/openapi)")
    empty = [k for k in ("orgId", "tblId", "itmId", "objL1") if not _s(cfg, k)]
    if empty:
        missing.append("kosis_config.json còn để trống: " + ", ".join(empty))
    prd = _s(cfg, "prdSe")
    if not prd:
        missing.append("kosis_config.json: prdSe còn trống (Y = năm, M = tháng)")
    elif prd not in ("Y", "M"):
        missing.append(f"kosis_config.json: prdSe = '{prd}' chưa hỗ trợ (chỉ nhận Y hoặc M, "
                       "vì trang chỉ nhận kỳ dạng YYYY hoặc YYYY-MM)")
    if _s(cfg, "startPrdDe") and not _s(cfg, "endPrdDe") or _s(cfg, "endPrdDe") and not _s(cfg, "startPrdDe"):
        missing.append("kosis_config.json: startPrdDe và endPrdDe phải điền cả hai hoặc bỏ trống cả hai")
    try:
        if int(cfg.get("newestPrdCnt") or 1) < 1:
            raise ValueError
    except (TypeError, ValueError):
        missing.append("kosis_config.json: newestPrdCnt phải là số nguyên >= 1")
    return missing


def not_ready_message(missing):
    return ("DỪNG: KOSIS chưa sẵn sàng, chưa lấy số liệu nào.\n"
            "Còn thiếu:\n" + "\n".join(f"  - {m}" for m in missing) + "\n"
            "Cách điền: xem INSTALL_IT.md, mục \"Điền mã bảng KOSIS\" "
            "(cũng có hướng dẫn ngắn ngay trong kosis_config.json).\n"
            "Không tự đoán mã bảng. Các bước khác của hệ thống vẫn chạy bình thường.")


# ----------------------------------------------------------------------------
# GỌI KOSIS
# ----------------------------------------------------------------------------
KOSIS_ERR_HINT = {
    "10": "khóa API không đúng", "11": "khóa API hết hạn",
    "20": "thiếu tham số bắt buộc (xem lại orgId/tblId/itmId/objL/prdSe)",
    "21": "tham số không hợp lệ (xem lại mã trong kosis_config.json)",
    "30": "không có dữ liệu cho lựa chọn này (xem lại objL/itmId/kỳ)",
    "31": "kết quả quá lớn, hãy thu hẹp lựa chọn (objL) hoặc giảm số kỳ",
}


def build_params(cfg, key, so_ky=None):
    p = {"method": "getList", "apiKey": key, "format": "json", "jsonVD": "Y",
         "orgId": _s(cfg, "orgId"), "tblId": _s(cfg, "tblId"),
         "itmId": _s(cfg, "itmId"), "prdSe": _s(cfg, "prdSe")}
    for n in range(1, MAX_AXES + 1):
        p[f"objL{n}"] = _s(cfg, f"objL{n}")
    if _s(cfg, "startPrdDe") and _s(cfg, "endPrdDe") and not so_ky:
        p["startPrdDe"], p["endPrdDe"] = _s(cfg, "startPrdDe"), _s(cfg, "endPrdDe")
    else:
        p["newestPrdCnt"] = str(so_ky or int(cfg.get("newestPrdCnt") or 1))
    return p


def fetch(cfg, key, so_ky=None, http_get=None, retries=3, sleep=time.sleep):
    """Gọi KOSIS, trả về list dòng dữ liệu. http_get cho phép thay bằng bản giả khi thử."""
    if http_get is None:
        try:
            import requests
        except ImportError:
            raise KosisError("Thiếu thư viện requests. Cài: pip install -r requirements.txt")
        http_get = requests.get
        net_errors = (requests.RequestException,)
    else:
        net_errors = (OSError,)
    url = _s(cfg, "api_url") or DEFAULT_API_URL
    params = build_params(cfg, key, so_ky)

    last = ""
    for attempt in range(1, retries + 1):
        try:
            resp = http_get(url, params=params, timeout=60)
        except net_errors as e:
            last = f"lỗi mạng: {_mask(e, key)}"
        else:
            if resp.status_code >= 500:
                last = f"KOSIS trả mã HTTP {resp.status_code}"
            elif resp.status_code != 200:
                raise KosisError(f"KOSIS trả mã HTTP {resp.status_code} (không thử lại).")
            else:
                return _parse_response(resp, key)
        if attempt < retries:
            sleep(3 * attempt)
    raise KosisError(f"Gọi KOSIS thất bại sau {retries} lần: {last}")


def _parse_response(resp, key):
    try:
        data = resp.json()
    except ValueError:
        raise KosisError("KOSIS trả về dữ liệu không đọc được (không phải JSON): "
                         + _mask(resp.text[:200], key).replace("\n", " "))
    if isinstance(data, dict):
        code = str(data.get("err", ""))
        msg = _mask(data.get("errMsg", ""), key)
        if code or msg:
            hint = KOSIS_ERR_HINT.get(code)
            raise KosisError(f"KOSIS báo lỗi (mã {code or '?'}): {msg}" + (f" — gợi ý: {hint}" if hint else ""))
        data = [data]
    if not isinstance(data, list) or not data:
        raise KosisError("KOSIS trả về rỗng — kiểm tra lại objL/itmId/kỳ trong kosis_config.json.")
    return data


# ----------------------------------------------------------------------------
# BIẾN ĐỔI DỮ LIỆU KOSIS -> DÒNG stat
# ----------------------------------------------------------------------------
def _fields(cfg):
    f = {"gia_tri": "DT", "ky": "PRD_DE", "don_vi": "UNIT_NM", "ten_bang": "TBL_NM"}
    f.update({k: v for k, v in (cfg.get("ten_truong") or {}).items() if v})
    return f


def _axis_name(cfg_value, n_axes, what):
    v = str(cfg_value or "").strip().upper()
    if not v:
        return None
    m = re.fullmatch(r"C?(\d)", v)
    if not m or not (1 <= int(m.group(1)) <= MAX_AXES):
        raise KosisError(f"kosis_config.json: {what} = '{cfg_value}' không hợp lệ (dạng đúng: C1..C{MAX_AXES}).")
    n = int(m.group(1))
    if n not in n_axes:
        raise KosisError(f"kosis_config.json: {what} = C{n} nhưng dữ liệu KOSIS chỉ có các chiều "
                         + ", ".join(f"C{i}" for i in n_axes) + ".")
    return n


def detect_axes(rec0, cfg):
    """Xác định chiều nào là tỉnh, quốc tịch, giới tính. Mơ hồ thì dừng, không đoán."""
    n_axes = [n for n in range(1, MAX_AXES + 1) if f"C{n}_NM" in rec0]
    if not n_axes:
        raise KosisError("Dữ liệu KOSIS không có chiều phân loại nào (không thấy trường C1_NM). "
                         "Các trường nhận được: " + ", ".join(sorted(rec0)))
    tinh = _axis_name(cfg.get("truc_tinh"), n_axes, "truc_tinh")
    qt = _axis_name(cfg.get("truc_quoc_tich"), n_axes, "truc_quoc_tich")
    gt = _axis_name(cfg.get("truc_gioi_tinh"), n_axes, "truc_gioi_tinh")

    def by_hint(hints, exclude):
        hits = [n for n in n_axes if n not in exclude
                and any(h in _norm(rec0.get(f"C{n}_OBJ_NM", "")) for h in hints)]
        return hits

    def pick(current, hints, exclude, label, cfg_key, required):
        if current is not None:
            return current
        hits = by_hint(hints, exclude)
        if len(hits) == 1:
            return hits[0]
        names = ", ".join(f"C{n}='{rec0.get(f'C{n}_OBJ_NM', '')}'" for n in n_axes)
        if not hits and not required:
            return None
        why = "không thấy" if not hits else "thấy nhiều chiều khớp"
        raise KosisError(f"Không xác định được chiều {label} ({why}). Các chiều trong dữ liệu: {names}. "
                         f"Hãy điền \"{cfg_key}\" trong kosis_config.json (ví dụ \"C1\").")

    taken = {n for n in (tinh, qt, gt) if n}
    qt = pick(qt, HINT_NATIONALITY, taken, "quốc tịch", "truc_quoc_tich", True)
    taken.add(qt)
    gt = pick(gt, HINT_SEX, taken, "giới tính", "truc_gioi_tinh", False)
    if gt:
        taken.add(gt)
    tinh = pick(tinh, HINT_PROVINCE, taken, "tỉnh/thành", "truc_tinh", True)
    taken.add(tinh)
    if len({tinh, qt}) < 2 or (gt and gt in (tinh, qt)):
        raise KosisError("Hai chiều được gán trùng nhau (tỉnh/quốc tịch/giới tính). Kiểm tra truc_* trong kosis_config.json.")
    return tinh, qt, gt, [n for n in n_axes if n not in taken]


def _parse_value(v):
    """Số nguyên từ ô DT của KOSIS; None nếu ô trống/bị ẩn ('-', 'X', ...)."""
    if v is None:
        return None
    t = str(v).replace(",", "").strip()
    if not re.fullmatch(r"\d+(\.0+)?", t):
        return None
    return int(float(t))


def _period(raw, prd_se):
    r = str(raw).strip()
    if prd_se == "Y" and re.fullmatch(r"\d{4}", r):
        return r
    if prd_se == "M" and re.fullmatch(r"\d{6}", r) and 1 <= int(r[4:]) <= 12:
        return f"{r[:4]}-{r[4:]}"
    raise KosisError(f"Kỳ '{r}' không khớp prdSe='{prd_se}' (Y cần YYYY, M cần YYYYMM). Kiểm tra prdSe trong kosis_config.json.")


def transform(records, cfg):
    """Trả về (danh_sách_dòng_stat, thông_tin). Ném KosisError khi dữ liệu không khớp."""
    f = _fields(cfg)
    rec0 = records[0]
    for need in ("gia_tri", "ky"):
        if f[need] not in rec0:
            raise KosisError(f"Dữ liệu KOSIS không có trường '{f[need]}'. Các trường nhận được: "
                             + ", ".join(sorted(rec0)) + ". Sửa \"ten_truong\" trong kosis_config.json nếu tên đã đổi.")
    tinh, qt, gt, extra_axes = detect_axes(rec0, cfg)
    prd_se = _s(cfg, "prdSe")
    viet = [_norm(x) for x in cfg.get("nhan_viet_nam") or ["베트남"]]
    tong = {_norm(x) for x in cfg.get("nhan_tong") or ["계"]}
    nu = {_norm(x) for x in cfg.get("nhan_nu") or ["여자"]}
    nam = {_norm(x) for x in cfg.get("nhan_nam") or ["남자"]}

    info = {"records": len(records), "viet": 0, "unmapped": set(), "missing_value": 0,
            "other_sex": 0, "nationalities_seen": [], "axes": (tinh, qt, gt)}
    cells = {}          # (area, period) -> {"tong"/"nam"/"nu": giá trị}
    cell_rows = {}      # để báo trùng: (area, period, giới) -> các bản ghi
    seen_nat = []
    for rec in records:
        unit = _norm(rec.get(f["don_vi"], ""))
        if unit not in OK_UNITS:
            raise KosisError(f"Đơn vị của bảng là '{rec.get(f['don_vi'])}', không phải 'người (명)'. "
                             "Script không tự đổi đơn vị để tránh sai số; hãy chọn bảng/mục tính theo người.")
        nat = _norm(rec.get(f"C{qt}_NM"))
        if nat not in seen_nat:
            seen_nat.append(nat)
        if not any(nat.startswith(v) for v in viet):
            continue  # quốc tịch khác: không lấy, không cộng vào đâu cả
        info["viet"] += 1

        area = PROVINCE_MAP.get(_norm(rec.get(f"C{tinh}_NM")))
        if area is None:
            info["unmapped"].add(str(rec.get(f"C{tinh}_NM")))
            continue
        period = _period(rec.get(f["ky"]), prd_se)
        val = _parse_value(rec.get(f["gia_tri"]))
        if val is None:
            info["missing_value"] += 1
            continue

        if gt:
            sx = _norm(rec.get(f"C{gt}_NM"))
            sk = "tong" if sx in tong else "nu" if sx in nu else "nam" if sx in nam else None
            if sk is None:
                info["other_sex"] += 1
                continue
        else:
            sk = "tong"
        slot = cells.setdefault((area, period), {})
        if sk in slot:
            others = sorted({f"C{n} ({rec.get(f'C{n}_OBJ_NM', '?')})" for n in extra_axes})
            raise KosisError(
                f"Một ô bị trùng số liệu: {area}, kỳ {period}, mục '{sk}' có từ 2 dòng KOSIS trở lên. "
                + ("Thường do chiều chưa được chốt về mục 'Tổng/계': " + ", ".join(others) + ". " if others else "")
                + "Hãy sửa objL/itmId trong kosis_config.json cho mỗi chiều chỉ còn một mục cần dùng.")
        slot[sk] = val

    if info["viet"] == 0:
        raise KosisError("Không thấy mục 'Việt Nam' (" + ", ".join(cfg.get("nhan_viet_nam") or ["베트남"])
                         + f") trong chiều quốc tịch C{qt}. Các quốc tịch có trong dữ liệu: "
                         + ", ".join(seen_nat[:15]) + ". Kiểm tra objL hoặc sửa \"nhan_viet_nam\".")
    if not cells:
        raise KosisError("Không có dòng nào của Việt Nam khớp tên tỉnh/thành. Tên vùng chưa nhận ra: "
                         + ", ".join(sorted(info["unmapped"])[:15])
                         + ". Có thể bảng là cấp quận/huyện, hoặc cần thêm tên vào PROVINCE_MAP trong kosis_ingest.py.")

    link = _s(cfg, "link_bang") or (f"https://kosis.kr/statHtml/statHtml.do?orgId={_s(cfg, 'orgId')}"
                                    f"&tblId={_s(cfg, 'tblId')}")
    name = _s(cfg, "ten_bang") or str(rec0.get(f["ten_bang"], "")).strip() or f"bảng {_s(cfg, 'tblId')}"
    src = f"KOSIS · {name} · {link}"

    rows = []
    for (area, period), s in sorted(cells.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        value = s.get("tong")
        if value is None and "nam" in s and "nu" in s:
            value = s["nam"] + s["nu"]
        if value is None:
            info["missing_value"] += 1
            continue
        row = {"kind": "stat", "metric": METRIC, "area": area, "period": period, "value": value}
        if "nu" in s:
            if s["nu"] > value:
                raise KosisError(f"Số nữ ({s['nu']}) lớn hơn tổng ({value}) ở {area}, kỳ {period}: "
                                 "dữ liệu không khớp, kiểm tra lại lựa chọn giới tính.")
            row["female"] = s["nu"]
        row["src"] = src
        row["confidence"] = "chính thức"
        rows.append(row)
    if not rows:
        raise KosisError("Có dòng của Việt Nam nhưng không dựng được số liệu nào (thiếu số hoặc thiếu mục 'Tổng').")
    info["nationalities_seen"] = seen_nat
    return rows, info


def write_jsonl_atomic(rows, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def report(rows, info, out=sys.stdout):
    periods = sorted({r["period"] for r in rows})
    print(f"[KOSIS] {info['records']} dòng thô, {info['viet']} dòng Việt Nam -> {len(rows)} dòng stat "
          f"({len({r['area'] for r in rows})} vùng, kỳ: {', '.join(periods)}).", file=out)
    if info["unmapped"]:
        names = sorted(info["unmapped"])
        print(f"[KOSIS] bỏ qua {len(names)} tên vùng không phải tỉnh/thành đã biết "
              f"(thường là cấp quận/huyện): {', '.join(names[:6])}{'…' if len(names) > 6 else ''}", file=out)
    if info["missing_value"]:
        print(f"[KOSIS] lưu ý: {info['missing_value']} ô không có số (bị ẩn hoặc trống), đã bỏ.", file=out)
    if info["other_sex"]:
        print(f"[KOSIS] lưu ý: {info['other_sex']} dòng có mục giới tính lạ, đã bỏ.", file=out)


def run(cfg, key, out_path, dry_run=False, so_ky=None, http_get=None, out=sys.stdout, err=sys.stderr):
    """Trả về mã thoát."""
    missing = check_ready(cfg, key)
    if missing:
        print(not_ready_message(missing), file=err)
        return EXIT_NOT_READY
    try:
        records = fetch(cfg, key, so_ky, http_get)
        rows, info = transform(records, cfg)
    except KosisError as e:
        print("LỖI KOSIS: " + _mask(e, key), file=err)
        return EXIT_KOSIS
    report(rows, info, out)
    if dry_run:
        print("[KOSIS] --dry-run: không ghi file. Vài dòng đầu:", file=out)
        for r in rows[:5]:
            print("   " + json.dumps(r, ensure_ascii=False), file=out)
        return 0
    write_jsonl_atomic(rows, out_path)
    print(f"[KOSIS] Đã ghi {out_path}", file=out)
    return 0


# ----------------------------------------------------------------------------
# CHẠY THỬ OFFLINE — dữ liệu GIẢ LẬP
# ----------------------------------------------------------------------------
# ĐÂY LÀ PHẢN HỒI GIẢ LẬP do người viết code tự dựng để thử logic; KHÔNG phải số liệu
# thật và không biết có đúng từng chữ với KOSIS thật hay không. Mã bảng, mã mục (TEST_*,
# G*, N*) và mọi con số (1000, 600, 99999...) đều là bịa để thử, không mang ý nghĩa thống kê.
# Dạng dữ liệu mô phỏng theo mô tả OpenAPI của KOSIS: một list, mỗi phần tử là một ô với
# C<n>/C<n>_OBJ_NM/C<n>_NM cho từng chiều, ITM_*, UNIT_NM, PRD_SE, PRD_DE, DT (chuỗi).
def _fake_cell(tinh, nat, sex, dt, period="202509", unit="명"):
    return {"ORG_ID": "TEST_ORG", "TBL_ID": "TEST_TBL", "TBL_NM": "[GIẢ LẬP] Bảng thử: quốc tịch x tỉnh x giới tính",
            "C1": "G-" + tinh, "C1_OBJ_NM": "행정구역별", "C1_NM": tinh,
            "C2": "N-" + nat, "C2_OBJ_NM": "국적별", "C2_NM": nat,
            "C3": "S-" + sex, "C3_OBJ_NM": "성별", "C3_NM": sex,
            "ITM_ID": "TEST_ITM", "ITM_NM": "외국인수", "UNIT_NM": unit,
            "PRD_SE": "M", "PRD_DE": period, "DT": dt}


def _fake_response():
    recs = []
    # (tên tỉnh Hàn, tổng VN, nữ VN, tổng Trung Quốc giả)
    data = [("전국", 5000, 2900), ("서울특별시", 400, 250), ("경기도", 1000, 600),
            ("강원특별자치도", 50, 20), ("전북특별자치도", 70, 30), ("제주특별자치도", 30, 10),
            ("충청남도", 200, 90)]
    for tinh, tot, fem in data:
        for sex, v in (("계", tot), ("남자", tot - fem), ("여자", fem)):
            recs.append(_fake_cell(tinh, "베트남", sex, str(v)))
        recs.append(_fake_cell(tinh, "중국", "계", "99999"))     # quốc tịch khác: phải bị loại
        recs.append(_fake_cell(tinh, "태국", "여자", "88888"))
    recs.append(_fake_cell("경기도 안산시", "베트남", "계", "777"))  # cấp quận/huyện: phải bị bỏ qua
    recs.append(_fake_cell("부산광역시", "베트남", "계", "-"))        # ô bị ẩn: phải bị bỏ, có đếm
    recs.append(_fake_cell("경기도", "베트남", "계", "1,100", period="202508"))  # kỳ khác, có dấu phẩy
    return recs


def self_test():
    import copy
    import io
    import tempfile
    import export_for_page as ex

    cfg = {"orgId": "TEST_ORG", "tblId": "TEST_TBL", "itmId": "TEST_ITM", "objL1": "ALL", "objL2": "ALL",
           "objL3": "ALL", "prdSe": "M", "newestPrdCnt": 2, "ten_bang": "", "link_bang": "",
           "nhan_viet_nam": ["베트남"]}

    # 0) kosis_config.json đi kèm phải đọc được và đủ khóa (không đòi nó còn trống hay đã điền)
    shipped = load_config(DEFAULT_CONFIG)
    for k in ("orgId", "tblId", "itmId", "objL1", "prdSe", "newestPrdCnt", "ten_truong", "nhan_viet_nam"):
        assert k in shipped, f"kosis_config.json thiếu khóa {k}"

    # 1) logic chính trên dữ liệu giả lập
    rows, info = transform(_fake_response(), cfg)
    got = {(r["area"], r["period"]): r for r in rows}
    assert len(rows) == 8, [(r["area"], r["period"]) for r in rows]
    assert got[("Gyeonggi", "2025-09")]["value"] == 1000 and got[("Gyeonggi", "2025-09")]["female"] == 600
    assert got[("Gyeonggi", "2025-08")]["value"] == 1100 and "female" not in got[("Gyeonggi", "2025-08")]
    assert got[("Toàn quốc", "2025-09")]["value"] == 5000
    for tên, area in (("강원특별자치도", "Gangwon"), ("전북특별자치도", "Jeolla Bắc"), ("제주특별자치도", "Jeju"),
                      ("충청남도", "Chungcheong Nam"), ("서울특별시", "Seoul")):
        assert (area, "2025-09") in got, f"thiếu {tên} -> {area}"
    assert not any(r["value"] in (99999, 88888, 777) for r in rows), "lẫn quốc tịch khác / cấp quận"
    assert ("Busan", "2025-09") not in got and info["missing_value"] == 1
    assert info["unmapped"] == {"경기도 안산시"}
    for r in rows:
        assert r["kind"] == "stat" and r["metric"] == METRIC and r["confidence"] == "chính thức"
        assert "[GIẢ LẬP]" in r["src"] and "https://kosis.kr/statHtml/statHtml.do?orgId=TEST_ORG&tblId=TEST_TBL" in r["src"]
        ex.validate_row(r)  # phải qua được bộ kiểm tra của export_for_page.py

    # 2) bảng chỉ có nam/nữ, không có "tổng": value = nam + nữ
    recs = [_fake_cell("서울특별시", "베트남", "남자", "300"), _fake_cell("서울특별시", "베트남", "여자", "200")]
    r2, _ = transform(recs, cfg)
    assert r2[0]["value"] == 500 and r2[0]["female"] == 200

    # 3) bảng không có chiều giới tính: không có female
    recs = [{k: v for k, v in c.items() if not k.startswith("C3")} for c in
            [_fake_cell("서울특별시", "베트남", "계", "321"), _fake_cell("서울특별시", "중국", "계", "5")]]
    r3, i3 = transform(recs, cfg)
    assert len(r3) == 1 and r3[0]["value"] == 321 and "female" not in r3[0] and i3["axes"][2] is None

    # 4) chiều thừa chưa chốt "Tổng" -> báo trùng, dừng, nêu tên chiều thừa
    recs = [_fake_cell("서울특별시", "베트남", "계", "10"), _fake_cell("서울특별시", "베트남", "계", "20")]
    for r in recs:
        r["C4"], r["C4_OBJ_NM"] = "X", "체류자격별"
    recs[0]["C4_NM"], recs[1]["C4_NM"] = "A", "B"
    try:
        transform(recs, cfg)
        raise AssertionError("đáng lẽ phải báo trùng")
    except KosisError as e:
        assert "trùng" in str(e) and "C4" in str(e) and "체류자격별" in str(e), str(e)

    # 5) không thấy Việt Nam -> dừng, in ra các quốc tịch đang có
    try:
        transform([_fake_cell("서울특별시", "중국", "계", "5")], cfg)
        raise AssertionError("đáng lẽ phải báo không thấy Việt Nam")
    except KosisError as e:
        assert "Việt Nam" in str(e) and "중국" in str(e)

    # 6) đơn vị lạ -> dừng
    try:
        transform([_fake_cell("서울특별시", "베트남", "계", "5", unit="천명")], cfg)
        raise AssertionError("đáng lẽ phải báo đơn vị")
    except KosisError as e:
        assert "Đơn vị" in str(e)

    # 7) kỳ không khớp prdSe -> dừng
    try:
        transform([_fake_cell("서울특별시", "베트남", "계", "5", period="2025")], cfg)
        raise AssertionError("đáng lẽ phải báo kỳ")
    except KosisError as e:
        assert "prdSe" in str(e)

    # 8) mơ hồ về chiều -> dừng, không đoán
    bad = [dict(_fake_cell("서울특별시", "베트남", "계", "5"), C2_OBJ_NM="행정구역별")]
    try:
        transform(bad, cfg)
        raise AssertionError("đáng lẽ phải báo mơ hồ chiều")
    except KosisError as e:
        assert "truc_" in str(e)
    cfg_axes = dict(cfg, truc_tinh="C1", truc_quoc_tich="C2", truc_gioi_tinh="C3")
    transform(_fake_response(), cfg_axes)  # chỉ định tay thì chạy bình thường

    # 9) cấu hình trống/thiếu khóa -> DỪNG với mã 2, không gọi mạng
    called = []

    def never_http(*a, **k):
        called.append(1)
        raise AssertionError("không được gọi mạng khi chưa cấu hình")

    for c, k, must in ((dict(shipped, orgId="", tblId="", itmId="", objL1="", prdSe=""), "khoa-gia", "orgId, tblId, itmId, objL1"),
                       (cfg, "", "KOSIS_API_KEY"), ({}, "", "prdSe")):
        e = io.StringIO()
        code = run(c, k, "x", http_get=never_http, out=io.StringIO(), err=e)
        assert code == EXIT_NOT_READY and "DỪNG" in e.getvalue() and must in e.getvalue(), e.getvalue()
    assert not called

    # 10) chạy đủ đường với HTTP giả: ghi file, khóa không lọt vào log; lỗi KOSIS được dịch
    class FakeResp:
        def __init__(self, payload, status=200):
            self.status_code, self._p = status, payload
            self.text = json.dumps(payload, ensure_ascii=False)

        def json(self):
            return copy.deepcopy(self._p)

    seen_params = {}

    def ok_http(url, params=None, timeout=None):
        seen_params.update(params)
        seen_params["_url"] = url
        return FakeResp(_fake_response())

    secret = "SECRET-KEY-123"
    with tempfile.TemporaryDirectory() as tmp:
        out_path = os.path.join(tmp, "kosis_stats.jsonl")
        o, e = io.StringIO(), io.StringIO()
        assert run(cfg, secret, out_path, http_get=ok_http, out=o, err=e) == 0, e.getvalue()
        assert seen_params["apiKey"] == secret and seen_params["tblId"] == "TEST_TBL"
        assert seen_params["newestPrdCnt"] == "2" and seen_params["objL1"] == "ALL" and seen_params["objL4"] == ""
        assert seen_params["_url"] == DEFAULT_API_URL
        assert secret not in o.getvalue() + e.getvalue()
        with open(out_path, encoding="utf-8") as f:
            lines = [json.loads(x) for x in f]
        assert len(lines) == 8 and all(ex.validate_row(x)[0] == "stat" for x in lines)

        # --dry-run không ghi file
        out2 = os.path.join(tmp, "dry.jsonl")
        assert run(cfg, secret, out2, dry_run=True, http_get=ok_http, out=io.StringIO(), err=io.StringIO()) == 0
        assert not os.path.exists(out2)

        # KOSIS báo lỗi khóa: thông báo tiếng Việt, mã 3, không ghi file
        def err_http(url, params=None, timeout=None):
            return FakeResp({"err": "10", "errMsg": f"인증키 오류 {secret}"})
        e = io.StringIO()
        out3 = os.path.join(tmp, "err.jsonl")
        assert run(cfg, secret, out3, http_get=err_http, out=io.StringIO(), err=e) == EXIT_KOSIS
        assert "mã 10" in e.getvalue() and "khóa API" in e.getvalue() and secret not in e.getvalue()
        assert not os.path.exists(out3)

        # lỗi mạng: thử lại 3 lần rồi báo, và khóa trong thông báo lỗi bị che
        calls = []

        def net_http(url, params=None, timeout=None):
            calls.append(1)
            raise OSError(f"Max retries exceeded with url: /x?apiKey={secret}&tblId=T")
        e = io.StringIO()
        try:
            fetch(cfg, secret, http_get=net_http, sleep=lambda s: None)
            raise AssertionError("đáng lẽ phải lỗi")
        except KosisError as ex_:
            assert secret not in _mask(ex_, secret) and len(calls) == 3

    print("self-test: OK — ánh xạ tỉnh, tách riêng Việt Nam, female, báo trùng/mơ hồ/đơn vị, dừng khi chưa "
          "cấu hình, che khóa API. (Toàn bộ dữ liệu thử là GIẢ LẬP; chưa gọi KOSIS thật.)")


def main():
    p = argparse.ArgumentParser(description="Lấy số người Việt theo tỉnh/thành từ KOSIS (kind=stat).")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="file cấu hình (mặc định kosis_config.json cạnh script)")
    p.add_argument("--out", default="out/kosis_stats.jsonl")
    p.add_argument("--so-ky", type=int, help="lấy N kỳ gần nhất (ghi đè newestPrdCnt)")
    p.add_argument("--dry-run", action="store_true", help="gọi KOSIS thật, in thử vài dòng, không ghi file")
    p.add_argument("--self-test", action="store_true", help="chạy thử offline bằng dữ liệu giả lập")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    try:
        cfg = load_config(args.config)
    except KosisError as e:  # file cấu hình mất/hỏng là LỖI cần người xem, không phải "chưa cấu hình"
        print("LỖI: " + str(e), file=sys.stderr)
        return EXIT_KOSIS
    key = os.environ.get("KOSIS_API_KEY", "").strip()
    return run(cfg, key, args.out, args.dry_run, args.so_ky)


if __name__ == "__main__":
    sys.exit(main())
