#!/usr/bin/env python3
"""Thư viện dùng chung cho luồng quét doanh nghiệp từ nguồn dữ liệu mở.

Gồm: gọi HTTP có thử lại, ghi vào Lark Base bằng Lark Open API, khóa chống trùng,
gắn nhãn A/B/C theo luật, và vài hàm tiện ích. Chỉ dùng thư viện chuẩn của Python.
Không có khóa hay bí mật nào trong file này; khóa đọc từ biến môi trường.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable

VN_TZ = timezone(timedelta(hours=7))
VERSION = "0.1"

# Mã thoát chung cho mọi script
EXIT_OK = 0
EXIT_CONFIG = 1      # thiếu cấu hình hoặc biến môi trường
EXIT_BLOCKED = 2     # nguồn chặn hoặc giới hạn tốc độ: dừng và báo, không né
EXIT_PARTIAL = 3     # đã ghi được một phần vào Base rồi gặp lỗi
EXIT_API = 4         # Lark hoặc nguồn trả lỗi, chưa ghi gì


class ScanError(Exception):
    """Lỗi chung của luồng quét."""


class BlockedError(ScanError):
    """Nguồn từ chối (403) hoặc vẫn giới hạn tốc độ (429) sau khi chờ. Dừng, không né."""


class LarkError(ScanError):
    """Lark trả lỗi. `written` là số dòng đã ghi thành công trước khi lỗi."""

    def __init__(self, message: str, written: int = 0):
        super().__init__(message)
        self.written = written


# ---------------------------------------------------------------- HTTP

Transport = Callable[[str, str, dict, Any, int], "tuple[int, Any]"]


def default_transport(method: str, url: str, headers: dict, body: Any, timeout: int):
    """Gọi HTTP bằng urllib. Trả (mã trạng thái, JSON hoặc chuỗi)."""
    data = None
    hdrs = {"User-Agent": f"ihouzz-open-data-scan/{VERSION}", "Accept": "application/json"}
    hdrs.update(headers or {})
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json; charset=utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if "403" in reason:  # proxy hoặc tường lửa của công ty chặn: dừng và báo, không né
            raise BlockedError(f"Kết nối bị chặn (403) tới {url}: {reason}") from exc
        raise ScanError(f"Không kết nối được tới {url}: {reason}") from exc
    except TimeoutError as exc:
        raise ScanError(f"Hết thời gian chờ khi gọi {url}") from exc
    text = raw.decode("utf-8", errors="replace")
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


def http_call(
    transport: Transport,
    method: str,
    url: str,
    headers: dict | None = None,
    body: Any = None,
    timeout: int = 60,
    retries_5xx: int = 2,
    retries_429: int = 0,
    wait_429: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
):
    """Gọi HTTP có thử lại.

    - 403: ném BlockedError ngay (không thử lại, không né).
    - 429: chờ `wait_429` giây rồi thử lại tối đa `retries_429` lần; vẫn 429 thì ném BlockedError.
    - 5xx: thử lại tối đa `retries_5xx` lần với thời gian chờ tăng dần.
    """
    attempts_5xx = 0
    attempts_429 = 0
    while True:
        status, payload = transport(method, url, headers or {}, body, timeout)
        if status == 403:
            raise BlockedError(f"403 từ chối: {url}")
        if status == 429:
            if attempts_429 >= retries_429:
                raise BlockedError(f"429 giới hạn tốc độ: {url}")
            attempts_429 += 1
            sleep(wait_429)
            continue
        if status >= 500:
            if attempts_5xx >= retries_5xx:
                raise ScanError(f"HTTP {status} từ {url}")
            attempts_5xx += 1
            sleep(2.0 * attempts_5xx)
            continue
        if status >= 400:
            raise ScanError(f"HTTP {status} từ {url}: {str(payload)[:300]}")
        return payload


# ---------------------------------------------------------------- Lark Base

def norm_cell(value: Any) -> str:
    """Đưa giá trị ô của Lark về chuỗi (ô văn bản có thể trả danh sách đoạn)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        text = str(value.get("text") or value.get("name") or "")
        link = value.get("link") or value.get("url") or ""
        return f"{text} {link}".strip() if link and link != text else text
    if isinstance(value, list):
        parts = [norm_cell(v) for v in value]
        sep = "" if value and all(isinstance(v, dict) for v in value) else ","
        return sep.join(p for p in parts if p)
    return str(value)


class LarkBase:
    """Đọc và ghi một bảng Lark Base bằng Lark Open API (tenant access token)."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        app_token: str,
        table_id: str,
        domain: str = "https://open.larksuite.com",
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.app_id, self.app_secret = app_id, app_secret
        self.app_token, self.table_id = app_token, table_id
        self.domain = domain.rstrip("/")
        self.transport = transport or default_transport
        self.sleep = sleep
        self._tk: str | None = None
        self._exp = 0.0

    def _call(self, method: str, path: str, body: Any = None, auth: bool = True):
        headers = {}
        if auth:
            headers["Authorization"] = f"Bearer {self._token()}"
        # Lark là API của chính công ty: giới hạn tốc độ thì chờ rồi thử lại vài lần là bình thường.
        return http_call(
            self.transport, method, self.domain + path, headers, body,
            retries_5xx=2, retries_429=3, wait_429=5.0, sleep=self.sleep,
        )

    def _token(self) -> str:
        if self._tk and time.time() < self._exp - 60:
            return self._tk
        js = self._call(
            "POST", "/open-apis/auth/v3/tenant_access_token/internal",
            {"app_id": self.app_id, "app_secret": self.app_secret}, auth=False,
        )
        if not isinstance(js, dict) or js.get("code") != 0:
            raise LarkError(f"Không lấy được token Lark: {str(js)[:300]}")
        self._tk = js["tenant_access_token"]
        self._exp = time.time() + float(js.get("expire", 7200))
        return self._tk

    def _records_path(self) -> str:
        return f"/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"

    def list_all(self, page_size: int = 500, max_pages: int = 200) -> list[dict]:
        """Đọc toàn bộ bản ghi. Trả danh sách {tên cột: chuỗi}."""
        rows: list[dict] = []
        token = ""
        for _ in range(max_pages):
            path = self._records_path() + f"?page_size={page_size}"
            if token:
                path += f"&page_token={token}"
            js = self._call("GET", path)
            if js.get("code") != 0:
                raise LarkError(f"Đọc bảng lỗi: {js.get('code')} {js.get('msg')}")
            data = js.get("data") or {}
            for item in data.get("items") or []:
                fields = item.get("fields") or {}
                rows.append({k: norm_cell(v) for k, v in fields.items()})
            if not data.get("has_more"):
                return rows
            token = data.get("page_token") or ""
            if not token:
                return rows
        raise LarkError("Bảng quá lớn: vượt giới hạn số trang khi đọc")

    def batch_create(self, rows: list[dict], chunk: int = 100) -> int:
        """Ghi các dòng mới. Mỗi dòng là dict {tên cột: giá trị}. Trả số dòng ghi thành công."""
        written = 0
        for i in range(0, len(rows), chunk):
            part = rows[i:i + chunk]
            js = self._call(
                "POST", self._records_path() + "/batch_create",
                {"records": [{"fields": r} for r in part]},
            )
            if js.get("code") != 0:
                raise LarkError(
                    f"Ghi lô {i // chunk + 1} lỗi: {js.get('code')} {js.get('msg')} "
                    f"(đã ghi {written} dòng trước đó)",
                    written=written,
                )
            written += len(part)
        return written


# ---------------------------------------------------------------- Chuẩn hóa, chống trùng

_HANGUL = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힯]")


def has_hangul(text: str) -> bool:
    return bool(_HANGUL.search(text or ""))


def strip_accents(text: str) -> str:
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def norm_text(text: str) -> str:
    """Chữ thường, bỏ dấu, chỉ giữ chữ và số (giữ cả chữ Hàn), nối bằng một khoảng trắng."""
    t = strip_accents(text).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", t).split())


def norm_phone(text: str) -> str:
    """8 chữ số cuối của số điện thoại (bỏ qua mã nước). Rỗng nếu quá ngắn."""
    digits = re.sub(r"\D+", "", text or "")
    return digits[-8:] if len(digits) >= 8 else ""


_RE_PLACE = re.compile(r"place_id:([\w-]+)")
_RE_UEN = re.compile(r"[?&]q=([0-9A-Za-z]{8,10})(?=$|[&\s)\]])")


def ids_from_link(link: str) -> set[str]:
    """Lấy mã định danh nguồn từ cột 'Link nguồn' (Google place_id của lô thử cũ, UEN của ACRA).

    Không dùng cả đường link làm khóa: nhiều dòng từ cùng một trang danh bạ có thể chung link.
    """
    out = set()
    for m in _RE_PLACE.finditer(link or ""):
        out.add("pid:" + m.group(1))
    for m in _RE_UEN.finditer(link or ""):
        out.add("uen:" + m.group(1).upper())
    return out


def dedupe_keys(name: str = "", address: str = "", phone: str = "", link: str = "",
                region: str = "") -> set[str]:
    """Các khóa chống trùng của một doanh nghiệp: mã nguồn, số điện thoại, tên + địa chỉ.

    Khi chưa có địa chỉ thì dùng tên + khu vực (thô hơn, nhưng đỡ ghi trùng).
    """
    keys = set(ids_from_link(link))
    p = norm_phone(phone)
    if p:
        keys.add("ph:" + p)
    n, a = norm_text(name), norm_text(address)
    if n and a:
        keys.add(f"na:{n}|{a}")
    elif n and region:
        keys.add(f"nr:{n}|{norm_text(region)}")
    return keys


def existing_keys(rows: Iterable[dict], cols: dict) -> set[str]:
    keys: set[str] = set()
    for r in rows:
        keys |= dedupe_keys(
            r.get(cols["name"], ""), r.get(cols["address"], ""),
            r.get(cols["phone"], ""), r.get(cols["link"], ""), r.get(cols["region"], ""),
        )
    return keys


def count_pairs(rows: Iterable[dict], cols: dict) -> dict:
    """Đếm số dòng theo (Khu vực, Ngành); dùng để báo cáo."""
    out: dict = {}
    for r in rows:
        k = (r.get(cols["region"], ""), r.get(cols["industry"], ""))
        out[k] = out.get(k, 0) + 1
    return out


# ---------------------------------------------------------------- Ngày, nhãn

def scan_timestamp_ms(day: date | None = None) -> int:
    """Mili giây của 12:00 giờ Việt Nam (UTC+7) ngày `day` (mặc định hôm nay theo giờ VN)."""
    day = day or datetime.now(VN_TZ).date()
    return int(datetime(day.year, day.month, day.day, 12, 0, tzinfo=VN_TZ).timestamp() * 1000)


def _contains_word(norm_name: str, phrase: str) -> bool:
    p = norm_text(phrase)
    if not p:
        return False
    return re.search(rf"(?<!\w){re.escape(p)}(?!\w)", norm_name) is not None


def viet_signal(name: str, signals: dict) -> str:
    """Trả 'strong', 'weak' hoặc '' tùy tên có từ khóa Việt Nam rõ ràng, yếu hay không có."""
    n = norm_text(name)
    raw = name or ""
    for phrase in signals.get("strong", []):
        if _contains_word(n, phrase) or (has_hangul(phrase) and phrase in raw):
            return "strong"
    for phrase in signals.get("weak", []):
        if _contains_word(n, phrase) or (has_hangul(phrase) and phrase in raw):
            return "weak"
    return ""


def label_directory_row(name: str, has_contact: bool, signals: dict) -> tuple[str, str]:
    """Nhãn A/B/C cho dòng lấy từ danh bạ công khai. Trả (nhãn, lý do)."""
    sig = viet_signal(name, signals)
    if has_hangul(name):
        return "C", ("Tên tiếng Hàn: nhiều khả năng chủ là người Hàn dù có thể bán đồ hoặc món Việt. "
                     "Chưa xác nhận chủ.")
    if sig == "strong" and has_contact:
        return "A", "Tên có từ khóa Việt Nam rõ ràng và nguồn công bố liên hệ. Chưa xác nhận chủ là người Việt."
    if sig == "strong":
        return "B", "Tên có từ khóa Việt Nam nhưng nguồn không công bố liên hệ. Chưa xác nhận chủ."
    if sig == "weak":
        return "B", "Tên chỉ có từ khóa yếu về Việt Nam. Chưa xác nhận chủ."
    return "B", "Nguồn là danh bạ công khai nhưng tên không có dấu hiệu rõ về Việt Nam. Chưa xác nhận chủ."


def industry_from_name(name: str, rules: list[dict], default: str = "Chưa rõ ngành") -> str:
    """Suy ngành từ từ khóa trong tên (ghi rõ 'theo tên' vì chỉ là suy đoán)."""
    n = norm_text(name)
    for rule in rules:
        if any(_contains_word(n, w) for w in rule.get("words", [])):
            return rule["label"]
    return default


# ---------------------------------------------------------------- Cấu hình, log

def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def require_env(names: list[str]) -> dict:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise ScanError("Thiếu biến môi trường: " + ", ".join(missing))
    return {n: os.environ[n] for n in names}


def setup_logging(log_dir: str | None, name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        fh = logging.FileHandler(
            os.path.join(log_dir, datetime.now(VN_TZ).strftime("%Y-%m") + ".log"), encoding="utf-8"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


def make_lark(cfg: dict, transport: Transport | None = None) -> LarkBase:
    env = require_env(["LARK_APP_ID", "LARK_APP_SECRET"])
    base = cfg["base"]
    return LarkBase(
        env["LARK_APP_ID"], env["LARK_APP_SECRET"], base["app_token"], base["table_id"],
        domain=os.environ.get("LARK_DOMAIN") or base.get("lark_domain", "https://open.larksuite.com"),
        transport=transport,
    )


def build_row(cols: dict, *, name: str, region: str, industry: str, source: str, link: str,
              label: str, reason: str, address: str = "", phone: str = "", website: str = "",
              email: str = "", day: date | None = None) -> dict:
    """Dựng một dòng ghi vào Base. Cột bỏ trống thì không gửi. Không có cột nào cho
    Quy mô, Trạng thái duyệt, Nhận xét TGĐ (để TGĐ tự điền)."""
    row = {
        cols["name"]: name,
        cols["region"]: region,
        cols["industry"]: industry,
        cols["scan_date"]: scan_timestamp_ms(day),
        cols["source"]: source,
        cols["link"]: link,
        cols["label"]: label,
        cols["reason"]: reason,
    }
    optional = {
        cols["address"]: address, cols["phone"]: phone,
        cols["website"]: website, cols["email"]: email,
    }
    row.update({k: v for k, v in optional.items() if v})
    return row
