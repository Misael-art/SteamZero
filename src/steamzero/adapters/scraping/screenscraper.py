# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter para ScreenScraper.fr — a espinha dorsal do scraping.

API v2 (``https://www.screenscraper.fr/api2/jeuInfos.php``):
- Matching por SHA1, MD5, CRC32, nome de ROM, Title ID.
- Tipos de mídia: box-2D, box-3D, box-scan, wheel, wheel-hd, screenshot,
  screenshot-title, fanart, video, marquee, support-texture, manuel, map, flyer.
- Autenticação por ``devid``/``devpassword`` (conta desenvolvedor, grátis)
  e ``ssid``/``sspassword`` (conta de usuário, para cotas elevadas).

Rate limits: 50k req/dia (grátis), até +5 threads por €10/mês.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from steamzero.adapters.scraping.base import BaseMediaProvider, RateLimiter
from steamzero.core.errors import SteamZeroError
from steamzero.ports import GameIdentity, MediaCandidate

_API_BASE = "https://www.screenscraper.fr/api2"
_API_PATH = "jeuInfos.php"

_PLATFORM_MAP: dict[str, int | str] = {
    "3do": "1",
    "amiga": "105",
    "amstradcpc": "107",
    "android": "310",
    "apple2": "108",
    "arcade": "75",
    "atari2600": "27",
    "atari5200": "28",
    "atari7800": "29",
    "atarijaguar": "30",
    "atarilynx": "31",
    "atarist": "106",
    "bbc": "110",
    "c64": "40",
    "cd32": "111",
    "cdtv": "129",
    "coleco": "32",
    "cps1": "76",
    "cps2": "77",
    "cps3": "78",
    "daphne": "82",
    "desktop": "135",
    "dolphin": "83",
    "dos": "84",
    "dreamcast": "23",
    "fds": "99",
    "gameandwatch": "33",
    "gameboy": "9",
    "gameboyadvance": "12",
    "gameboycolor": "10",
    "gamegear": "21",
    "gamingplatform": "500",
    "gmaster": "109",
    "gx4000": "130",
    "intellivision": "34",
    "j2me": "123",
    "mastersystem": "18",
    "megacd": "36",
    "megadrive": "1",
    "msx": "38",
    "n64": "6",
    "nds": "11",
    "neogeo": "25",
    "neogeocd": "42",
    "nes": "3",
    "ngp": "41",
    "ngpc": "41",
    "openbor": "131",
    "pcengine": "35",
    "pcenginecd": "42",
    "pcenginefx": "132",
    "pcfx": "39",
    "pico8": "133",
    "playstation": "2",
    "playstation2": "15",
    "playstation3": "134",
    "playstation4": "296",
    "playstation5": "502",
    "playstationportable": "13",
    "playstationvita": "104",
    "psx": "2",
    "satellaview": "136",
    "saturn": "4",
    "sega32x": "20",
    "segacd": "36",
    "sg1000": "114",
    "snes": "4",
    "steam": "135",
    "sufami": "137",
    "supergrafx": "132",
    "switch": "311",
    "tg16": "35",
    "tgcd": "42",
    "triforce": "139",
    "vectrex": "43",
    "vic20": "115",
    "videopac": "116",
    "virtualboy": "26",
    "wii": "14",
    "wiiu": "138",
    "windows": "135",
    "wonderswan": "24",
    "wonderswancolor": "24",
    "xbox": "22",
    "xbox360": "140",
    "xboxone": "300",
    "xboxseries": "499",
    "zmachine": "118",
    "zx81": "117",
    "zxspectrum": "37",
}

_MEDIA_KIND_MAP: dict[str, str] = {
    "boxart": "box-2D",
    "boxart3d": "box-3D",
    "boxartfull": "box-scan",
    "wheel": "wheel",
    "wheelhd": "wheel-hd",
    "screenshot": "ss",
    "title": "sstitle",
    "fanart": "fanart",
    "video": "video",
    "marquee": "marquee",
    "cartridge": "support-texture",
    "manual": "manuel",
    "map": "map",
    "flyer": "flyer",
}

_SUPPORTED_KINDS = frozenset(_MEDIA_KIND_MAP)


class ScreenScraperAdapter(BaseMediaProvider):
    """Adapter para ScreenScraper.fr API v2.

    Requer credenciais ``devid``/``devpassword`` (conta desenvolvedor obrigatória)
    e opcionalmente ``ssid``/``sspassword`` (conta de usuário para cota elevada).
    """

    def __init__(
        self,
        *,
        devid: str | None = None,
        devpassword: str | None = None,
        ssid: str | None = None,
        sspassword: str | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__(rate_limiter=rate_limiter)
        self._devid = devid
        self._devpassword = devpassword
        self._ssid = ssid
        self._sspassword = sspassword

    @property
    def name(self) -> str:
        return "screenscraper"

    def supported_kinds(self) -> frozenset[str]:
        return _SUPPORTED_KINDS

    def supported_platforms(self) -> frozenset[str]:
        return frozenset(_PLATFORM_MAP)

    def search(
        self,
        identity: GameIdentity,
        media_kinds: list[str],
        region_priority: list[str] | None = None,
    ) -> list[MediaCandidate]:
        if self._devid is None or self._devpassword is None:
            raise SteamZeroError(
                "E-SCRAPE-CREDENTIAL-MISSING",
                detail="ScreenScraper requer devid e devpassword configurados",
            )

        self._rate_limit()
        params = self._build_params(identity)
        url = f"{_API_BASE}/{_API_PATH}?{urlencode(params)}"
        raw = self._fetch_url(url)

        try:
            root = ET.fromstring(raw)  # noqa: S314 — trusted API, not user input
        except ET.ParseError as exc:
            raise SteamZeroError(
                "E-SCRAPE-CORRUPT-MEDIA",
                detail=f"resposta XML inválida do ScreenScraper: {exc}",
            ) from exc

        data = root.find("jeu")
        if data is None:
            err = root.find("error")
            if err is not None:
                code_elem = err.find("code")
                code = code_elem.text if code_elem is not None else err.text
                if code in ("429", "rate limit"):
                    raise SteamZeroError("E-SCRAPE-RATE-LIMITED", detail=f"ScreenScraper: {code}")
                if code in ("403", "quota"):
                    raise SteamZeroError("E-SCRAPE-QUOTA-EXCEEDED", detail=f"ScreenScraper: {code}")
            return []

        candidates: list[MediaCandidate] = []
        kinds_to_fetch = set(media_kinds) & _SUPPORTED_KINDS
        for kind in kinds_to_fetch:
            accepted_types = _accepted_media_types(kind)
            for media in data.iter("media"):
                typ = (media.get("type") or "").lower()
                if typ not in accepted_types:
                    continue
                url_text = media.findtext("url", "").strip()
                if not url_text:
                    continue
                url_text = url_text.replace("http://", "https://")
                crc = media.findtext("crc", "").strip()
                region = media.get("region", "") or media.findtext("region", "")
                region_code = _region_normalize(region) if region else None
                language = media.findtext("language", "") or None
                try:
                    width = int(media.get("width", 0) or 0) or None
                    height = int(media.get("height", 0) or 0) or None
                except (ValueError, TypeError):
                    width = height = None
                if kind == "wheel":
                    confidence = 0.9 if "hd" in url_text.lower() else 0.8
                else:
                    confidence = 1.0 if identity.serial or identity.hashes else 0.85
                candidates.append(
                    MediaCandidate(
                        url=url_text,
                        media_kind=kind,
                        provider=self.name,
                        confidence=confidence,
                        width=width,
                        height=height,
                        region=region_code,
                        language=language,
                        license="CC-BY-NC-SA",
                        attribution="ScreenScraper.fr",
                        hash=crc or None,
                    )
                )

        if region_priority and len(candidates) > 1:
            candidates.sort(
                key=lambda c: (
                    region_priority.index(c.region) if c.region in region_priority else 99,
                    -c.confidence,
                )
            )
        else:
            candidates.sort(key=lambda c: -c.confidence)

        return candidates

    def _build_params(self, identity: GameIdentity) -> dict[str, str]:
        if self._devid is None or self._devpassword is None:
            raise SteamZeroError("E-SCRAPE-CREDENTIAL-MISSING")
        params = {
            "devid": self._devid,
            "devpassword": self._devpassword,
            "softname": "steamzero",
            "output": "xml",
        }
        if self._ssid is not None and self._sspassword is not None:
            params["ssid"] = self._ssid
            params["sspassword"] = self._sspassword

        platform_id = _PLATFORM_MAP.get(identity.platform_slug)
        if platform_id is not None:
            params["systemeid"] = str(platform_id)

        sha1 = identity.hashes.get("sha1")
        md5 = identity.hashes.get("md5")
        crc = identity.hashes.get("crc32")

        if sha1:
            params["sha1"] = sha1
        elif md5:
            params["md5"] = md5
        elif crc:
            params["crc"] = crc
        elif identity.title_id:
            params["romnom"] = identity.title_id
        elif identity.serial:
            params["serial"] = identity.serial
        else:
            params["romnom"] = identity.title

        return params


def _region_normalize(region: str) -> str:
    region_map = {
        "us": "us",
        "usa": "us",
        "eu": "eu",
        "europe": "eu",
        "jp": "jp",
        "japan": "jp",
        "br": "br",
        "brazil": "br",
        "wor": "wor",
        "as": "as",
        "asia": "as",
    }
    return region_map.get(region.strip().lower(), region.strip().lower())


def _accepted_media_types(kind: str) -> frozenset[str]:
    types = {
        "boxart": frozenset({"box-2d", "box-2d-side", "box-2d-back"}),
        "boxart3d": frozenset({"box-3d", "box-3d-side", "box-3d-back"}),
        "boxartfull": frozenset({"box-scan"}),
        "wheel": frozenset({"wheel", "wheel-hd"}),
        "wheelhd": frozenset({"wheel-hd"}),
        "screenshot": frozenset({"ss", "ss-hd"}),
        "title": frozenset({"sstitle"}),
        "fanart": frozenset({"fanart", "fanart-hd"}),
        "video": frozenset({"video", "video-normalized"}),
        "marquee": frozenset({"marquee"}),
        "cartridge": frozenset({"support-texture"}),
        "manual": frozenset({"manuel"}),
        "map": frozenset({"map"}),
        "flyer": frozenset({"flyer"}),
    }
    result = types.get(kind, frozenset({_MEDIA_KIND_MAP.get(kind, kind)}))
    return result
