# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Provedor game-stream: Sunshine como codificador, Moonlight como receptor.

Descobre receptores Moonlight na LAN, faz pareamento via protocolo GFE,
gerencia sessao via API HTTP do Sunshine e aplica qualidade adaptativa.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.core.errors import SteamZeroError
from steamzero.core.fs import ensure_dir, write_atomic_text
from steamzero.core.paths import state_home
from steamzero.core.secret import Secret
from steamzero.ports import (
    CaptureConsent,
    CastCapabilities,
    LinkSample,
    ReceiverDescriptor,
)

_SUNSHINE_DEFAULT_PORT = 47989
_SUNSHINE_API_TIMEOUT = 5.0
_SUNSHINE_START_RETRIES = 20
_SUNSHINE_START_POLL_SEC = 0.5
_GFE_DISCOVERY_PORT = 47999
_RECEIVER_HTTP_PORT = 48010
_SESSIONS_FILE = "game-stream-sessions.jsonl"


@dataclass(frozen=True)
class _SunshineSession:
    session_id: str
    receiver_id: str


class GameStreamProvider:
    """Provedor game-stream via Sunshine + Moonlight.

    Gerencia o motor Sunshine como servico local, descobre receptores
    Moonlight na rede local e coordena sessoes de streaming. A sessao
    e persistida em disco e sobrevive a reinicio da interface: um novo
    ``GameStreamProvider`` encontra sessoes ativas pelo journal
    (``sessions()``) e verifica cada uma contra o Sunshine.
    """

    def __init__(
        self,
        sunshine_url: str = f"http://127.0.0.1:{_SUNSHINE_DEFAULT_PORT}",
        sunshine_binary: str = "sunshine",
        data_dir: Path | None = None,
    ) -> None:
        self._sunshine_url = sunshine_url.rstrip("/")
        self._sunshine_binary = sunshine_binary
        self._data_dir = data_dir or state_home()
        self._session: _SunshineSession | None = None
        self._sessions_path = self._data_dir / _SESSIONS_FILE

    @property
    def protocol(self) -> str:
        return "game-stream"

    def local_capabilities(self) -> CastCapabilities:
        try:
            info = self._sunshine_api("GET", "/api/serverinfo")
        except SteamZeroError:
            info = {}
        vcodecs: tuple[str, ...] = ("h264",)
        acodecs: tuple[str, ...] = ("opus",)
        hw_encoder = False
        full_screen = False
        if isinstance(info, dict):
            caps = {str(k).lower(): v for k, v in info.items()}
            vcodecs = tuple(caps.get("video_codecs", ("h264",)))
            acodecs = tuple(caps.get("audio_codecs", ("opus",)))
            hw_encoder = bool(caps.get("hardware_encoder", False))
            full_screen = bool(caps.get("display_capture", False))
        if not vcodecs:
            vcodecs = ("h264",)
        if not acodecs:
            acodecs = ("opus",)
        return CastCapabilities(
            full_screen=full_screen,
            application_window=self._pipewire_screencast_available(),
            system_audio=True,
            hardware_encoder=hw_encoder or self._vaapi_available(),
            max_width=3840,
            max_height=2160,
            max_frame_rate=60,
            video_codecs=vcodecs,
            audio_codecs=acodecs,
            input_back_channel=True,
        )

    def preflight(self) -> tuple[bool, str]:
        if self._sunshine_running():
            return True, ""
        if self._sunshine_binary_available():
            return True, ""
        return False, "engine-missing"

    def discover(self, timeout_ms: int = 5000) -> Sequence[ReceiverDescriptor]:
        receivers: list[ReceiverDescriptor] = []
        seen: set[str] = set()
        timeout_sec = max(0.1, timeout_ms / 1000.0)
        deadline = time.monotonic() + timeout_sec
        try:
            for host, port in self._mdns_discover(deadline):
                key = f"{host}:{port}"
                if key not in seen:
                    seen.add(key)
                    desc = self._probe_receiver(host, port)
                    if desc is not None:
                        receivers.append(desc)
        except OSError:
            pass
        return receivers

    def pair(self, receiver_id: str, pin: Secret | None = None) -> bool:
        host, port = self._parse_receiver_id(receiver_id)
        if pin is None:
            try:
                pin_data = self._sunshine_api("POST", "/api/pin")
                if isinstance(pin_data, dict):
                    raw = str(pin_data.get("pin", ""))
                else:
                    return False
            except SteamZeroError:
                return False
        else:
            raw = pin.reveal()
        try:
            url = f"http://{host}:{port}/pair"
            body = json.dumps({"pin": raw}).encode()
            req = urllib.request.Request(  # noqa: S310
                url, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=_SUNSHINE_API_TIMEOUT) as resp:  # noqa: S310
                return bool(resp.status == 200)
        except (OSError, urllib.error.URLError):
            return False

    def start(
        self,
        receiver_id: str,
        profile_id: str,
        mode: str,
        consent: CaptureConsent,
    ) -> str:
        if not consent.granted:
            raise SteamZeroError(
                "E-CAST-CONSENT-REQUIRED",
                detail="captura sem autorizacao do usuario",
            )
        payload: dict[str, object] = {
            "receiver_id": receiver_id,
            "profile_id": profile_id,
            "mode": mode,
        }
        if consent.audio:
            payload["audio"] = True
        try:
            result = self._sunshine_api("POST", "/api/stream", payload)
        except SteamZeroError as exc:
            raise SteamZeroError(
                "E-CAST-ENGINE-MISSING",
                detail=f"sunshine nao iniciou a sessao: {exc.detail}",
            ) from exc
        if not isinstance(result, dict):
            raise SteamZeroError(
                "E-CAST-ENGINE-MISSING",
                detail="resposta inesperada do sunshine",
            )
        sid = str(result.get("session_id", receiver_id))
        self._session = _SunshineSession(session_id=sid, receiver_id=receiver_id)
        self._persist_session(sid, receiver_id)
        return sid

    def sample(self, session_id: str) -> LinkSample | None:
        try:
            data = self._sunshine_api("GET", f"/api/stream/{session_id}/statistics")
        except SteamZeroError:
            return None
        if not isinstance(data, dict):
            return None
        return LinkSample(
            rtt_ms=int(data.get("rtt_ms", 0)),
            jitter_ms=int(data.get("jitter_ms", 0)),
            packet_loss_pct=float(data.get("packet_loss", 0.0)),
            decoder_queue_frames=int(data.get("decoder_queue", 0)),
            encoder_ms=float(data.get("encoder_ms", 0.0)),
            dropped_frames=int(data.get("dropped_frames", 0)),
        )

    def session_phase(self, session_id: str) -> tuple[str, str]:
        return ("streaming", "") if self._session_alive(session_id) else ("failed", "link-lost")

    def apply_stream(self, session_id: str, profile_id: str, bitrate_kbps: int) -> bool:
        try:
            result = self._sunshine_api(
                "POST",
                f"/api/stream/{session_id}",
                {"profile_id": profile_id, "bitrate_kbps": bitrate_kbps},
            )
            if isinstance(result, dict):
                return result.get("status") == "ok"
            return False
        except SteamZeroError:
            return False

    def request_keyframe(self, session_id: str) -> bool:
        try:
            result = self._sunshine_api("POST", f"/api/stream/{session_id}/keyframe")
            if isinstance(result, dict):
                return result.get("status") == "ok"
            return False
        except SteamZeroError:
            return False

    def stop(self, session_id: str) -> None:
        with suppress(SteamZeroError):
            self._sunshine_api("POST", "/api/stop", {"session_id": session_id})
        if self._session is not None and self._session.session_id == session_id:
            self._session = None
        self._forget_session(session_id)

    def sessions(self) -> Sequence[str]:
        active: list[str] = []
        for entry in self._load_sessions():
            sid = entry.get("session_id", "")
            if sid and self._session_alive(sid):
                active.append(sid)
        return active

    def _session_alive(self, session_id: str) -> bool:
        try:
            self._sunshine_api("GET", f"/api/stream/{session_id}/statistics")
            return True
        except SteamZeroError:
            return False

    def _persist_session(self, session_id: str, receiver_id: str) -> None:
        ensure_dir(self._sessions_path.parent)
        line = json.dumps(
            {"session_id": session_id, "receiver_id": receiver_id},
            sort_keys=True,
        )
        previous = self._sessions_path.read_text() if self._sessions_path.is_file() else ""
        write_atomic_text(self._sessions_path, previous + line + "\n")

    def _forget_session(self, session_id: str) -> None:
        remaining = [e for e in self._load_sessions() if e.get("session_id") != session_id]
        text = "".join(json.dumps(e, sort_keys=True) + "\n" for e in remaining)
        ensure_dir(self._sessions_path.parent)
        write_atomic_text(self._sessions_path, text)

    def _load_sessions(self) -> list[dict[str, str]]:
        if not self._sessions_path.is_file():
            return []
        try:
            raw = self._sessions_path.read_text()
            entries: list[dict[str, str]] = []
            for line in raw.strip().splitlines():
                if line:
                    entry = json.loads(line)
                    entries.append(entry)
            return entries
        except (OSError, json.JSONDecodeError):
            return []

    # --- Sunshine management -----------------------------------------------

    def ensure_running(self) -> bool:
        if self._sunshine_running():
            return True
        return self._start_sunshine()

    def _sunshine_running(self) -> bool:
        try:
            req = urllib.request.Request(  # noqa: S310
                f"{self._sunshine_url}/api/serverinfo",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=_SUNSHINE_API_TIMEOUT) as resp:  # noqa: S310
                return bool(resp.status == 200)
        except (OSError, urllib.error.URLError):
            return False

    def _sunshine_binary_available(self) -> bool:
        binary = self._sunshine_binary
        if Path(binary).is_file():
            return True
        try:
            env = os.environ.copy()
            result = subprocess.run(  # noqa: S603
                ["which", binary],  # noqa: S607
                capture_output=True,
                timeout=5,
                env=env,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _start_sunshine(self) -> bool:
        binary = self._sunshine_binary
        try:
            proc = subprocess.Popen(  # noqa: S603
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(_SUNSHINE_START_RETRIES):
                if self._sunshine_running():
                    return True
                time.sleep(_SUNSHINE_START_POLL_SEC)
            with suppress(Exception):
                proc.terminate()
            return False
        except OSError:
            return False

    def stop_sunshine(self) -> None:
        try:
            req = urllib.request.Request(  # noqa: S310
                f"{self._sunshine_url}/api/stop",
                method="POST",
                data=b"{}",
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=_SUNSHINE_API_TIMEOUT)  # noqa: S310
        except (OSError, urllib.error.URLError):
            pass

    # --- Descoberta de receptores ------------------------------------------

    def _mdns_discover(self, deadline: float) -> list[tuple[str, int]]:
        results: list[tuple[str, int]] = []
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)
        try:
            discovery_msg = b"STEAMZERO_DISCOVER"
            sock.sendto(discovery_msg, ("<broadcast>", _GFE_DISCOVERY_PORT))
            while time.monotonic() < deadline:
                try:
                    data, addr = sock.recvfrom(1024)
                    text = data.decode("utf-8", errors="replace")
                    if "STEAMZERO_RECEIVER" in text or addr[0]:
                        results.append((addr[0], _RECEIVER_HTTP_PORT))
                except TimeoutError:
                    continue
        finally:
            sock.close()
        return results

    def _probe_receiver(self, host: str, port: int) -> ReceiverDescriptor | None:
        url = f"http://{host}:{port}/info"
        try:
            req = urllib.request.Request(url, method="GET")  # noqa: S310
            with urllib.request.urlopen(req, timeout=2.0) as resp:  # noqa: S310
                if resp.status != 200:
                    return None
                body = resp.read().decode("utf-8")
                data = json.loads(body)
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            return None
        rid = str(data.get("receiver_id", f"{host}:{port}"))
        name = str(data.get("display_name", f"Moonlight ({host})"))
        transport = str(data.get("transport", "lan"))
        paired = bool(data.get("paired", False))
        caps_data = data.get("capabilities", {})
        if not isinstance(caps_data, dict):
            caps_data = {}
        caps = CastCapabilities(
            full_screen=bool(caps_data.get("full_screen", True)),
            application_window=bool(caps_data.get("application_window", True)),
            input_back_channel=bool(caps_data.get("input_back_channel", False)),
            max_width=int(caps_data.get("max_width", 1920)),
            max_height=int(caps_data.get("max_height", 1080)),
            max_frame_rate=int(caps_data.get("max_frame_rate", 60)),
            video_codecs=tuple(caps_data.get("video_codecs", ("h264",))),
            audio_codecs=tuple(caps_data.get("audio_codecs", ("opus",))),
            hardware_encoder=True,
        )
        return ReceiverDescriptor(
            receiver_id=rid,
            display_name=name,
            protocol="game-stream",
            address=f"{host}:{port}",
            transport=(
                transport if transport in {"wired", "lan", "wifi-direct", "unknown"} else "lan"
            ),
            paired=paired,
            capabilities=caps,
        )

    # --- Utilitarios -------------------------------------------------------

    def _sunshine_api(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
    ) -> dict[str, Any] | list[Any]:
        url = f"{self._sunshine_url}{path}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
        req = urllib.request.Request(  # noqa: S310
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=_SUNSHINE_API_TIMEOUT) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8")
                if not raw:
                    return {}
                result: dict[str, Any] | list[Any] = json.loads(raw)
                return result
        except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise SteamZeroError(
                "E-CAST-ENGINE-MISSING",
                detail=f"falha na api sunshine: {exc}",
            ) from exc
        except urllib.error.URLError as exc:
            raise SteamZeroError(
                "E-CAST-LINK-LOST",
                detail=f"sunshine inalcancavel: {exc}",
            ) from exc

    @staticmethod
    def _parse_receiver_id(receiver_id: str) -> tuple[str, int]:
        if ":" in receiver_id:
            host, port_str = receiver_id.rsplit(":", 1)
            try:
                return host, int(port_str)
            except ValueError:
                pass
        return receiver_id, _RECEIVER_HTTP_PORT

    @staticmethod
    def _vaapi_available() -> bool:
        try:
            result = subprocess.run(
                ["vainfo"],  # noqa: S607
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def _pipewire_screencast_available() -> bool:
        try:
            result = subprocess.run(
                ["pw-cli", "info"],  # noqa: S607
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
