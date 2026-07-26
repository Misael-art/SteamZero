# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Orquestrador de sessoes de compartilhamento de tela.

Coordena o ciclo completo: descoberta -> resolucao -> selecao -> negociacao ->
inicio -> monitoramento -> degradacao/recuperacao -> parada. Conecta o dominio
puro (``domain.screencast``) ao provedor concreto (``adapters.game_stream``).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar

from steamzero.adapters.game_stream import GameStreamProvider
from steamzero.adapters.screencast_web import WebReceiverProvider
from steamzero.core.errors import SteamZeroError
from steamzero.core.secret import Secret
from steamzero.domain.screencast import (
    CastMode,
    CastSession,
    CastState,
    FaultKind,
    QualityProfile,
    guard_consent,
    negotiate,
    plan_quality,
    plan_recovery,
    profile_for,
    resolve_receiver,
    select_target,
)
from steamzero.ports import (
    CaptureConsent,
    CastCapabilities,
    ReceiverDescriptor,
    ScreenCastProviderPort,
)


class CastOrchestrator:
    """Coordena o ciclo completo de uma sessao de compartilhamento de tela.

    Instancia unica, dona do provedor e do estado da sessao. Os metodos sao
    seguros para chamada serializada (cada requisicao HTTP completa antes da
    proxima). Nao use de multiplas threads concorrentes.
    """

    _PROVIDER_PROTOCOLS: ClassVar[dict[str, type[Any]]] = {
        "web-receiver": WebReceiverProvider,
        "game-stream": GameStreamProvider,
    }

    def __init__(self, data_dir: Path | None = None) -> None:
        self._providers: dict[str, ScreenCastProviderPort] = {}
        self._data_dir = data_dir

        self._session: CastSession | None = None
        self._provider_session_id: str | None = None
        self._active_protocol: str | None = None
        self._quality_profile: tuple[str, QualityProfile | None] = ("balanced", None)
        self._local_caps: CastCapabilities | None = None
        self._started_at: float = 0.0

        self._reconcile()

    # --- Provider lazy -------------------------------------------------------

    def _provider_for(self, protocol: str) -> ScreenCastProviderPort:
        if protocol not in self._providers:
            cls = self._PROVIDER_PROTOCOLS.get(protocol)
            if cls is None:
                raise SteamZeroError(
                    "E-CAST-UNKNOWN-PROTOCOL",
                    detail=f"protocolo desconhecido: {protocol}",
                )
            self._providers[protocol] = cls(data_dir=self._data_dir)
        return self._providers[protocol]

    def _all_providers(self) -> list[ScreenCastProviderPort]:
        for protocol, cls in self._PROVIDER_PROTOCOLS.items():
            if protocol not in self._providers:
                self._providers[protocol] = cls(data_dir=self._data_dir)
        return list(self._providers.values())

    def _reconcile(self) -> None:
        """No startup, limpa sessoes orfas dos providers (UI reiniciou)."""
        for provider in self._all_providers():
            for sid in provider.sessions():
                with suppress(SteamZeroError):
                    provider.stop(sid)

    # --- Descoberta e pareamento ---------------------------------------------

    def discover_receivers(self, timeout_ms: int = 5000) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for provider in self._all_providers():
            for desc in provider.discover(timeout_ms):
                resolved = resolve_receiver(desc)
                results.append(
                    {
                        "receiver_id": resolved.receiver_id,
                        "display_name": resolved.display_name,
                        "protocol": resolved.protocol.value,
                        "transport": resolved.transport,
                        "paired": resolved.paired,
                        "supported_modes": [m.value for m in resolved.supported_modes],
                        "estimated_quality": resolved.estimated_quality.value,
                        "blocked_reason": resolved.blocked_reason or "",
                        "capabilities": {
                            "max_width": resolved.capabilities.max_width,
                            "max_height": resolved.capabilities.max_height,
                            "max_frame_rate": resolved.capabilities.max_frame_rate,
                        },
                    }
                )
        return results

    def pair_receiver(self, receiver_id: str, pin: Secret | None = None) -> bool:
        return any(p.pair(receiver_id, pin) for p in self._all_providers())

    # --- Ciclo de vida da sessao ---------------------------------------------

    def start_stream(
        self,
        receiver_id: str,
        profile_id: str = "balanced",
        mode: str = "game",
        consent: CaptureConsent | None = None,
    ) -> dict[str, Any]:
        descriptors: list[ReceiverDescriptor] = []
        provider_map: dict[str, ScreenCastProviderPort] = {}
        for prov in self._all_providers():
            for desc in prov.discover(3000):
                descriptors.append(desc)
                provider_map[desc.receiver_id] = prov

        target_desc = next((d for d in descriptors if d.receiver_id == receiver_id), None)
        if target_desc is None:
            raise SteamZeroError(
                "E-CAST-NO-RECEIVER",
                detail=f"receptor nao encontrado: {receiver_id}",
            )

        provider = provider_map[receiver_id]

        ready, reason = provider.preflight()
        if not ready:
            raise SteamZeroError(
                "E-CAST-ENGINE-MISSING",
                detail=reason or "motor de streaming nao disponivel",
            )

        resolved = resolve_receiver(target_desc)
        if resolved.blocked_reason:
            raise SteamZeroError(
                "E-CAST-RECEIVER-INCOMPATIBLE",
                detail=f"receptor bloqueado: {resolved.blocked_reason}",
            )

        try:
            cast_mode = CastMode(mode)
        except ValueError:
            cast_mode = CastMode.AUTOMATIC
        selection = select_target(cast_mode, (resolved,))

        local_caps = provider.local_capabilities()
        profile = profile_for(profile_id)
        stream = negotiate(profile, selection.receiver, local_caps, mode=selection.mode)

        effective_consent = consent if consent is not None else CaptureConsent(granted=False)
        guard_consent(effective_consent, selection.mode)

        sid = provider.start(
            receiver_id=selection.receiver.receiver_id,
            profile_id=stream.profile_id,
            mode=selection.mode.value,
            consent=effective_consent,
        )

        self._session = CastSession.opened(selection, stream, effective_consent)
        self._provider_session_id = sid
        self._active_protocol = target_desc.protocol
        self._quality_profile = (profile_id, profile)
        self._local_caps = local_caps
        self._started_at = time.monotonic()
        phase, _cause = provider.session_phase(sid)
        if phase == "streaming":
            self._session = self._session.moved_to(CastState.STREAMING)
        return self._public_session()

    def _active_provider(self) -> ScreenCastProviderPort:
        if self._active_protocol is not None:
            return self._provider_for(self._active_protocol)
        providers = self._all_providers()
        return providers[0] if providers else self._provider_for("game-stream")

    def stop_stream(self) -> None:
        if self._session is None:
            return
        if self._provider_session_id is not None:
            self._active_provider().stop(self._provider_session_id)
        self._session = self._session.moved_to(CastState.STOPPING)
        self._session = self._session.moved_to(CastState.IDLE)
        self._session = None
        self._provider_session_id = None
        self._active_protocol = None
        self._quality_profile = ("balanced", None)
        self._local_caps = None
        self._started_at = 0.0

    def session_status(self) -> dict[str, Any] | None:
        if self._session is None:
            return None
        provider = self._active_provider()

        sid = self._provider_session_id
        phase, cause = provider.session_phase(sid) if sid is not None else ("idle", "")
        if phase == "streaming" and self._session.state is CastState.NEGOTIATING:
            self._session = self._session.moved_to(CastState.STREAMING)
        if phase == "failed":
            self._session = self._session.moved_to(CastState.FAILED)
            return {**self._public_session(), "fault": cause or "capture-failed"}
        if phase == "negotiating":
            return self._public_session()

        alive = sid is not None and (
            self._session_alive(provider, sid)
        )
        if not alive or self._provider_session_id is None:
            self._session = self._session.moved_to(CastState.RECONNECTING)
            plan = plan_recovery(FaultKind.LINK_LOST)
            return {
                **self._public_session(),
                "fault": FaultKind.LINK_LOST.value,
                "recovery": [a.value for a in plan.actions],
            }

        sid = self._provider_session_id
        sample = provider.sample(sid)
        if sample is None:
            return self._public_session()

        _, profile = self._quality_profile
        if profile is None:
            profile = profile_for("balanced")
        decision = plan_quality(self._session.stream, profile, sample)
        self._session = self._session.with_quality(decision)

        if decision.action.value.startswith("reduce"):
            provider.apply_stream(sid, decision.stream.profile_id, decision.stream.bitrate_kbps)
        if decision.request_keyframe:
            provider.request_keyframe(sid)

        if self._started_at:
            self._session = replace(
                self._session, duration_seconds=int(time.monotonic() - self._started_at)
            )

        return self._public_session()

    def active_sessions(self) -> Sequence[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for provider in self._all_providers():
            for sid in provider.sessions():
                if provider.sample(sid) is not None:
                    result.append({"session_id": sid})
        return result

    def ensure_engine(self) -> bool:
        return any(p.ensure_running() for p in self._all_providers())

    # --- Helpers -------------------------------------------------------------

    @property
    def has_active_session(self) -> bool:
        return self._session is not None

    def _public_session(self) -> dict[str, Any]:
        return self._session.public() if self._session is not None else {}

    @staticmethod
    def _session_alive(provider: ScreenCastProviderPort, session_id: str) -> bool:
        try:
            return provider.sample(session_id) is not None
        except SteamZeroError:
            return False
