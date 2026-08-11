# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter para ScreenScraper.fr — a espinha dorsal do scraping.

API v2 (``https://www.screenscraper.fr/api2/jeuInfos.php``):
- Matching por SHA1, MD5, CRC32, nome de ROM, Title ID.
- Output principal: JSON (``output=json``); XML como fallback.
- Autenticação por ``devid``/``devpassword`` (conta desenvolvedor, grátis)
  e ``ssid``/``sspassword`` (conta de usuário, para cotas elevadas).

Estrutura JSON: ``{"response":{"jeu":{"medias":[{"type":"...","url":"..."}]}}}``

Estrutura XML fallback: ``<Data><jeu><medias><media ...>URL</media></medias></jeu></Data>``

Rate limits: 50k req/dia (grátis), até +5 threads por €10/mês.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from steamzero.adapters.scraping.base import BaseMediaProvider, RateLimiter
from steamzero.core.errors import SteamZeroError
from steamzero.core.net import HttpClient
from steamzero.ports import GameIdentity, MediaCandidate

_API_BASE = "https://www.screenscraper.fr/api2"
_API_PATH = "jeuInfos.php"
_API_TEST_PATH = "ssuserInfos.php"

_PLATFORM_MAP: dict[str, int | str] = {
    # --- Nintendo ---
    "switch": "225",
    "nes": "3",
    "snes": "4",
    "n64": "14",
    "gamecube": "13",
    "wii": "16",
    "wiiu": "18",
    "n3ds": "17",
    "nds": "15",
    "fds": "106",
    "gameboy": "9",
    "gameboycolor": "10",
    "gameboyadvance": "12",
    "virtualboy": "11",
    "gameandwatch": "52",
    "pokemonmini": "211",
    # --- Sega ---
    "megadrive": "1",
    "mastersystem": "2",
    "saturn": "22",
    "dreamcast": "23",
    "gamegear": "21",
    "sega32x": "19",
    "megacd": "20",
    "segacd": "20",
    "sg1000": "109",
    # --- Sony ---
    "playstation": "57",
    "playstation2": "58",
    "playstation3": "59",
    "playstation4": "60",
    "playstation5": "502",
    "playstationportable": "61",
    "playstationvita": "62",
    # --- SNK ---
    "neogeo": "142",
    "neogeocd": "70",
    "ngp": "25",
    "ngpc": "82",
    # --- NEC ---
    "pcengine": "31",
    "pcenginecd": "114",
    "pcfx": "72",
    "supergrafx": "105",
    # --- Atari ---
    "atari2600": "26",
    "atari5200": "40",
    "atari7800": "41",
    "atarijaguar": "27",
    "atarilynx": "28",
    "atarist": "42",
    "atari800": "43",
    # --- Microsoft ---
    "xbox": "32",
    "xbox360": "33",
    "xboxone": "300",
    "xboxseries": "499",
    # --- Other consoles ---
    "3do": "29",
    "coleco": "48",
    "intellivision": "115",
    "vectrex": "102",
    "videopac": "104",
    # --- Arcade ---
    # cps1/cps2/cps3 saíram: os IDs que ocupavam (76/77/78) pertencem ao ZX
    # Spectrum e ao ZX81 na referência, e não há fonte para os IDs corretos do
    # Capcom Play System. Slug ausente omite ``systemeid`` e a busca degrada para
    # nome em todos os sistemas; slug com ID errado devolve o jogo de outro
    # sistema. Reinserir só com ID conferido contra payload real.
    "arcade": "75",
    # --- Bandai ---
    "wonderswan": "45",
    "wonderswancolor": "46",
    # --- Computer ---
    "amiga": "134",
    "amstradcpc": "65",
    "apple2": "86",
    "bbc": "37",
    "c64": "66",
    "cd32": "130",
    "desktop": "135",
    "steam": "135",
    "windows": "135",
    "dos": "135",
    "macintosh": "146",
    "msx": "113",
    "pico8": "234",
    "scummvm": "123",
    "zx81": "77",
    "zxspectrum": "76",
    # --- Handhelds & other ---
    "openbor": "214",
    "android": "310",
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
    """Adapter para ScreenScraper.fr API v2."""

    def __init__(
        self,
        *,
        devid: str | None = None,
        devpassword: str | None = None,
        ssid: str | None = None,
        sspassword: str | None = None,
        rate_limiter: RateLimiter | None = None,
        client: HttpClient | None = None,
    ) -> None:
        super().__init__(rate_limiter=rate_limiter, client=client)
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

    def test_connection(self) -> bool:
        if self._devid is None or self._devpassword is None:
            raise SteamZeroError(
                "E-SCRAPE-CREDENTIAL-MISSING",
                detail="ScreenScraper requer devid e devpassword configurados",
            )
        self._rate_limit()
        params = self._authentication_params()
        url = f"{_API_BASE}/{_API_TEST_PATH}?{urlencode(params)}"
        raw = self._fetch_url(url, max_bytes=256 * 1024)
        try:
            root = ET.fromstring(raw)  # noqa: S314 — trusted API, not user input
        except ET.ParseError as exc:
            raise SteamZeroError(
                "E-SCRAPE-CREDENTIAL-REJECTED",
                detail="ScreenScraper retornou uma resposta de autenticação inválida",
            ) from exc
        error = root.find(".//error")
        if error is not None:
            code = (error.findtext("code") or "").strip()
            if code == "429":
                raise SteamZeroError("E-SCRAPE-RATE-LIMITED")
            if code == "403":
                raise SteamZeroError("E-SCRAPE-QUOTA-EXCEEDED")
            raise SteamZeroError(
                "E-SCRAPE-CREDENTIAL-REJECTED",
                detail="ScreenScraper recusou as credenciais informadas",
            )
        return True

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

        body_text = raw.decode("utf-8", errors="replace")
        if body_text.startswith("Erreur"):
            return []

        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError:
            return self._search_from_xml(raw, identity, media_kinds, region_priority)

        jeu_raw = _json_get(payload, "response", "jeu")
        jeu: dict[str, object] = {}
        if isinstance(jeu_raw, dict):
            jeu = jeu_raw
        if not jeu:
            err = _json_get(payload, "error")
            if isinstance(err, dict):
                code = err.get("code", "")
                if code in ("429", "rate limit"):
                    raise SteamZeroError("E-SCRAPE-RATE-LIMITED", detail=f"ScreenScraper: {code}")
                if code in ("403", "quota"):
                    raise SteamZeroError("E-SCRAPE-QUOTA-EXCEEDED", detail=f"ScreenScraper: {code}")
                if code == "401":
                    raise SteamZeroError(
                        "E-SCRAPE-CREDENTIAL-REJECTED",
                        detail="ScreenScraper recusou as credenciais informadas",
                    )
            return []

        medias_raw = jeu.get("medias", [])
        medias_list: list[dict[str, object]] = medias_raw if isinstance(medias_raw, list) else []
        candidates: list[MediaCandidate] = []
        kinds_to_fetch = set(media_kinds) & _SUPPORTED_KINDS

        for kind in kinds_to_fetch:
            accepted_types = _accepted_media_types(kind)
            for media in medias_list:
                typ = str(media.get("type", "")).lower()
                if not typ or typ not in accepted_types:
                    continue
                url_text = str(media.get("url", "")).strip()
                if not url_text:
                    continue
                normalized_url = self._normalize_media_url(url_text)
                if normalized_url is None:
                    continue
                region = str(media.get("region", "")).strip()
                region_code = _region_normalize(region) if region else None
                language = str(media.get("language", "")) or None
                try:
                    width = int(str(media.get("width", 0) or 0)) or None
                    height = int(str(media.get("height", 0) or 0)) or None
                except (ValueError, TypeError):
                    width = height = None
                if kind == "wheel":
                    confidence = 0.9 if "hd" in normalized_url.lower() else 0.8
                else:
                    confidence = 1.0 if identity.serial or identity.hashes else 0.85
                candidates.append(
                    MediaCandidate(
                        url=normalized_url,
                        media_kind=kind,
                        provider=self.name,
                        confidence=confidence,
                        width=width,
                        height=height,
                        region=region_code,
                        language=language,
                        license="CC-BY-NC-SA",
                        attribution="ScreenScraper.fr",
                        hash=None,
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

    def _search_from_xml(
        self,
        raw: bytes,
        identity: GameIdentity,
        media_kinds: list[str],
        region_priority: list[str] | None = None,
    ) -> list[MediaCandidate]:
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
                if code == "401":
                    raise SteamZeroError(
                        "E-SCRAPE-CREDENTIAL-REJECTED",
                        detail="ScreenScraper recusou as credenciais informadas",
                    )
            return []

        candidates: list[MediaCandidate] = []
        kinds_to_fetch = set(media_kinds) & _SUPPORTED_KINDS
        for kind in kinds_to_fetch:
            accepted_types = _accepted_media_types(kind)
            for media in data.iter("media"):
                typ = (media.get("type") or "").lower()
                if typ not in accepted_types:
                    continue
                url_text = (media.text or "").strip()
                if not url_text:
                    url_text = media.findtext("url", "").strip()
                if not url_text:
                    continue
                normalized_url = self._normalize_media_url(url_text)
                if normalized_url is None:
                    continue
                region = media.get("region", "") or ""
                region_code = _region_normalize(region) if region else None
                language = media.get("language") or media.findtext("language", "") or None
                try:
                    width = int(media.get("width", 0) or 0) or None
                    height = int(media.get("height", 0) or 0) or None
                except (ValueError, TypeError):
                    width = height = None
                if kind == "wheel":
                    confidence = 0.9 if "hd" in normalized_url.lower() else 0.8
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
                        hash=None,
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
        params = self._authentication_params()
        params.update(
            {
                "output": "json",
                "romtype": "rom",
            }
        )

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

    def _authentication_params(self) -> dict[str, str]:
        if self._devid is None or self._devpassword is None:
            raise SteamZeroError("E-SCRAPE-CREDENTIAL-MISSING")
        params = {
            "devid": self._devid,
            "devpassword": self._devpassword,
            "softname": "steamzero",
        }
        if self._ssid is not None and self._sspassword is not None:
            params["ssid"] = self._ssid
            params["sspassword"] = self._sspassword
        return params


def _json_get(obj: object, *keys: str) -> object | None:
    current: object = obj
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


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
