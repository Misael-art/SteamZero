#!/usr/bin/env python3
"""Capture, sanitize, and dump ScreenScraper API responses for test fixtures.

Usage:
    export SCRAPER_DEVID=xxx
    export SCRAPER_DEVPASSWORD=yyy
    python tools/capture_screenscraper_payload.py

Output:
  - tests/fixtures/scraping/screenscraper/*.{json,xml}
  - tests/fixtures/scraping/screenscraper/raw/
  - stdout JSON structural dump
"""

from __future__ import annotations

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "scraping" / "screenscraper"
)
RAW_DIR = FIXTURE_DIR / "raw"
_API_BASE = "https://www.screenscraper.fr/api2"

_URL_REPLACE_COUNTER: dict[str, int] = {}
_CRED_PLACEHOLDER = "SANITIZED"

_CRED_RE = re.compile(
    r"(<(?:devid|devpassword|ssid|sspassword)>)(.*?)(</(?:devid|devpassword|ssid|sspassword)>)"
)
_URL_RE = re.compile(r"https://(?:[a-zA-Z0-9._-]+\.)+[a-zA-Z]{2,}(?:/[^\s<>\"]*)?")
_CRED_PARAM_RE = re.compile(r"(devid|devpassword|ssid|sspassword)=[^&\s<>\"]+")

# O bloco ssuser é a conta do operador (login, e-mail, cotas). Nada dele pode ir
# para um fixture versionado, então redigimos todo o texto folha dentro dele em
# vez de listar campo a campo — campo novo do provedor já nasce redigido.
_SSUSER_BLOCK_RE = re.compile(r"(<ssuser>)(.*?)(</ssuser>)", re.DOTALL)
_LEAF_TEXT_RE = re.compile(r"(<([a-zA-Z0-9_]+)>)([^<>]+)(</\2>)")


def _sanitize_url(url: str) -> str:
    ext = _ext_from_url(url)
    kind = _URL_REPLACE_COUNTER.get(ext, 0)
    _URL_REPLACE_COUNTER[ext] = kind + 1
    return f"https://example.com/screenscraper/{kind:02d}.{ext}"


_MEDIA_EXTS = frozenset({"png", "jpg", "jpeg", "webp", "mp4", "avi", "pdf", "gif", "php"})


def _ext_from_url(url: str) -> str:
    ext = url.rsplit(".", 1)[-1].split("?", 1)[0].split("#", 1)[0].lower()
    return ext if ext in _MEDIA_EXTS else "bin"


def _redact_ssuser_xml(text: str) -> str:
    def _block(match: re.Match[str]) -> str:
        inner = _LEAF_TEXT_RE.sub(
            lambda leaf: leaf.group(1) + _CRED_PLACEHOLDER + leaf.group(4), match.group(2)
        )
        return match.group(1) + inner + match.group(3)

    return _SSUSER_BLOCK_RE.sub(_block, text)


def _sanitize_xml(raw: bytes) -> bytes:
    text = raw.decode("utf-8", errors="replace")
    # Erase credential values from XML elements
    text = _CRED_RE.sub(r"\1" + _CRED_PLACEHOLDER + r"\3", text)
    # Erase the whole account block (login, quotas, contribution counters)
    text = _redact_ssuser_xml(text)

    # Replace media URLs with placeholders
    def _replace_url(m: re.Match) -> str:
        original = m.group(0)
        return _sanitize_url(original)

    text = _URL_RE.sub(_replace_url, text)
    # Also erase credentials from any URL query strings in text content
    text = _CRED_PARAM_RE.sub(r"\1=" + _CRED_PLACEHOLDER, text)
    return text.encode("utf-8")


def _sanitize_json(raw: bytes) -> bytes:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    _sanitize_json_obj(data)
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")


def _redact_leaves(obj: object) -> None:
    """Substitui todo valor escalar da subárvore — usado no bloco da conta."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, dict | list):
                _redact_leaves(v)
            else:
                obj[k] = _CRED_PLACEHOLDER
    elif isinstance(obj, list):
        for item in obj:
            _redact_leaves(item)


def _sanitize_json_obj(obj: object) -> None:
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k == "ssuser":
                _redact_leaves(v)
            elif k in ("devid", "devpassword", "ssid", "sspassword"):
                obj[k] = _CRED_PLACEHOLDER
            elif isinstance(v, str) and (v.startswith("http") or re.match(r"^https?://", v)):
                obj[k] = _sanitize_url(v)
            else:
                _sanitize_json_obj(v)
    elif isinstance(obj, list):
        for item in obj:
            _sanitize_json_obj(item)


def _xml_to_json_tree(elem: ET.Element, max_text: int = 120) -> object:
    children = list(elem)
    result: dict[str, object] = {
        "tag": elem.tag,
        "attrib": dict(elem.attrib),
    }
    if elem.text and elem.text.strip():
        text = elem.text.strip()
        if re.match(r"^https?://", text):
            result["_url"] = "[SANITIZED]" if "example.com" in text else text[:80]
            result["url_pattern"] = _ext_from_url(text)
        else:
            result["text"] = text[:max_text]
    if children:
        child_groups: dict[str, list[object]] = {}
        for child in children:
            child_groups.setdefault(child.tag, []).append(_xml_to_json_tree(child, max_text))
        result["children"] = child_groups
    return result


def _dump_structure(root: ET.Element) -> str:
    tree = _xml_to_json_tree(root)
    return json.dumps(tree, indent=2, ensure_ascii=False)


def _mask_url(url: str) -> str:
    return _CRED_PARAM_RE.sub(r"\1=***", url)


def _fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "SteamZero-Capture/0.1"})  # noqa: S310
    with urlopen(req, timeout=30) as resp:  # noqa: S310
        return resp.read()


def _capture_and_sanitize(name: str, url: str, raw_dir: Path) -> tuple[bytes | None, str]:
    """Fetch URL, save raw copy, sanitize, return (sanitized_bytes, extension)."""
    print(f"  Fetching {_mask_url(url)}")
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        raw = _fetch(url)
    except Exception as e:
        print(f"  ERROR: {e}")
        (raw_dir / f"{name}_error.txt").write_text(str(e))
        return None, "error"

    # Detect content type from URL/response
    is_json = "json" in url or raw[:1] == b"{"
    ext = "json" if is_json else "xml"

    raw_path = raw_dir / f"{name}.{ext}"
    raw_path.write_bytes(raw)
    print(f"  Raw saved: raw/{name}.{ext} ({len(raw)} bytes)")

    sanitized = _sanitize_json(raw) if is_json else _sanitize_xml(raw)

    fixture_path = FIXTURE_DIR / f"{name}.{ext}"
    fixture_path.write_bytes(sanitized)
    print(f"  Fixture: {fixture_path.name} ({len(sanitized)} bytes)")
    return sanitized, ext


def main() -> None:
    devid = os.environ.get("SCRAPER_DEVID")
    devpassword = os.environ.get("SCRAPER_DEVPASSWORD")
    ssid = os.environ.get("SCRAPER_SSID") or ""
    sspassword = os.environ.get("SCRAPER_SSPASSWORD") or ""
    if not devid or not devpassword:
        print("FATAL: set SCRAPER_DEVID and SCRAPER_DEVPASSWORD")
        sys.exit(1)

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / ".gitignore").write_text("raw/\n")

    base_params = {
        "devid": devid,
        "devpassword": devpassword,
        "softname": "steamzero-capture",
        "output": "json",
    }
    if ssid:
        base_params["ssid"] = ssid
    if sspassword:
        base_params["sspassword"] = sspassword

    queries = [
        ("ssuserInfos", {**base_params}),
        (
            "jeuInfos_by_name",
            {
                **base_params,
                "systemeid": "225",
                "romnom": "Super Mario Odyssey",
                "romtype": "rom",
            },
        ),
        (
            "jeuInfos_by_titleid",
            {
                **base_params,
                "systemeid": "225",
                "romnom": "0100000000010000",
                "romtype": "rom",
            },
        ),
        (
            "jeuInfos_notfound",
            {
                **base_params,
                "systemeid": "225",
                "romnom": "ZZZZ_NONEXISTENT_99999",
                "romtype": "rom",
            },
        ),
    ]

    results = {}
    for name, params in queries:
        endpoint = "ssuserInfos.php" if "ssuserInfos" in name else "jeuInfos.php"
        url = f"{_API_BASE}/{endpoint}?{urlencode(params)}"
        sanitized, ext = _capture_and_sanitize(name, url, RAW_DIR)
        if sanitized is not None and ext == "xml":
            try:
                root = ET.fromstring(sanitized)  # noqa: S314
                results[name] = _xml_to_json_tree(root)
            except ET.ParseError as exc:
                results[name] = {
                    "error": str(exc),
                    "raw_preview": sanitized[:200].decode("utf-8", errors="replace"),
                }
        elif sanitized is not None and ext == "json":
            try:
                results[name] = json.loads(sanitized)
            except json.JSONDecodeError as exc:
                results[name] = {
                    "error": str(exc),
                    "raw_preview": sanitized[:200].decode("utf-8", errors="replace"),
                }
        print()

    print("=" * 60)
    print("STRUCTURED DUMP (sanitized)")
    print("=" * 60)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
