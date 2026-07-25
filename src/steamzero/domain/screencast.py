# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Plataforma pura de compartilhamento de tela: capacidade, estado e resiliência.

Uma única função de produto ("Transmitir para a TV") sobre múltiplas vias
(ADR-0022). Este módulo não captura, não codifica e não fala com a rede — ele
DECIDE. Cada decisão é função pura para que degradação, reconexão e recuperação
sejam testáveis sem TV, sem rede e sem encoder.

Três invariantes atravessam o módulo:

1. Compatibilidade vem de capacidade observada, nunca de marca, modelo ou ano.
2. A qualidade cai antes de a sessão cair (P8: falha degrada, nunca trava).
3. Nome, endereço e PIN do receptor não atravessam o contrato público.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from steamzero.api import contracts
from steamzero.core import crypto
from steamzero.core.errors import SteamZeroError
from steamzero.ports import (
    CaptureConsent,
    CastCapabilities,
    LinkSample,
    ReceiverDescriptor,
)

# Piso de compatibilidade: negociado, jamais presumido acima disto.
MANDATORY_VIDEO_CODEC = "h264"
MANDATORY_AUDIO_CODEC = "opus"

# Backoff progressivo de reconexão (spec §12). O último degrau esgota a sessão.
RECONNECT_DELAYS_SECONDS = (0, 1, 2, 4, 8)


class CastProtocol(Enum):
    """Vias de transporte. O nome de produto na UI é separado do id interno."""

    GAME_STREAM = "game-stream"  # motor de baixa latência (encoder por hardware)
    STEAM_REMOTE_PLAY = "steam-remote-play"
    SCREEN_MIRROR = "screen-mirror"  # espelhamento (Miracast / Cast de tela)
    MEDIA_CAST = "media-cast"  # trailers, vídeos e músicas
    WEB_RECEIVER = "web-receiver"  # navegador local via WebRTC (loopback)


class CastMode(Enum):
    AUTOMATIC = "automatic"
    GAME = "game"
    GAME_WINDOW = "game-window"  # só o jogo: sem notificações nem senhas na TV
    MIRROR = "mirror"
    MEDIA = "media"


class CastState(Enum):
    IDLE = "idle"
    CHECKING_CAPABILITIES = "checkingCapabilities"
    DISCOVERING = "discovering"
    PAIRING = "pairing"
    NEGOTIATING = "negotiating"
    STREAMING = "streaming"
    DEGRADED = "degraded"
    RECOVERING = "recovering"
    RECONNECTING = "reconnecting"
    STOPPING = "stopping"
    FAILED = "failed"


class LinkQuality(Enum):
    UNKNOWN = "unknown"
    LIMITED = "limited"
    GOOD = "good"
    EXCELLENT = "excellent"


class QualityAction(Enum):
    HOLD = "hold"
    RAISE = "raise"
    REDUCE_BITRATE = "reduceBitrate"
    REDUCE_RESOLUTION = "reduceResolution"
    REDUCE_FRAME_RATE = "reduceFrameRate"


class FaultKind(Enum):
    ENCODER_LOST = "encoderLost"
    RESOLUTION_CHANGED = "resolutionChanged"
    AUDIO_DEVICE_CHANGED = "audioDeviceChanged"
    LINK_LOST = "linkLost"
    RECEIVER_RESTARTED = "receiverRestarted"
    HOST_SUSPENDED = "hostSuspended"
    GAME_EXITED = "gameExited"
    CONSENT_REVOKED = "consentRevoked"
    PROTECTED_CONTENT = "protectedContent"


class RecoveryAction(Enum):
    PAUSE_SEND = "pauseSend"
    REBUILD_ENCODER = "rebuildEncoder"
    RENEGOTIATE_STREAM = "renegotiateStream"
    RESTART_AUDIO = "restartAudio"
    RESYNC_CLOCK = "resyncClock"
    REQUEST_KEYFRAME = "requestKeyframe"
    BACKOFF_RECONNECT = "backoffReconnect"
    SWITCH_SOURCE_TO_LAUNCHER = "switchSourceToLauncher"
    SHOW_PROTECTED_NOTICE = "showProtectedNotice"
    STOP_CAPTURE = "stopCapture"
    RESUME_SEND = "resumeSend"


# --- Máquina de estados ----------------------------------------------------
# Regra estrutural (testada): nenhum estado é beco sem saída e IDLE é
# alcançável de qualquer estado. STREAMING nunca cai direto em IDLE — o
# desligamento passa por STOPPING para revogar captura em ordem.
_TRANSITIONS: dict[CastState, frozenset[CastState]] = {
    CastState.IDLE: frozenset({CastState.CHECKING_CAPABILITIES}),
    CastState.CHECKING_CAPABILITIES: frozenset(
        {CastState.DISCOVERING, CastState.IDLE, CastState.FAILED}
    ),
    CastState.DISCOVERING: frozenset(
        {CastState.PAIRING, CastState.NEGOTIATING, CastState.IDLE, CastState.FAILED}
    ),
    CastState.PAIRING: frozenset({CastState.NEGOTIATING, CastState.IDLE, CastState.FAILED}),
    CastState.NEGOTIATING: frozenset(
        {CastState.STREAMING, CastState.RECONNECTING, CastState.IDLE, CastState.FAILED}
    ),
    CastState.STREAMING: frozenset(
        {
            CastState.DEGRADED,
            CastState.RECOVERING,
            CastState.RECONNECTING,
            CastState.STOPPING,
            CastState.FAILED,
        }
    ),
    CastState.DEGRADED: frozenset(
        {
            CastState.STREAMING,
            CastState.RECOVERING,
            CastState.RECONNECTING,
            CastState.STOPPING,
            CastState.FAILED,
        }
    ),
    CastState.RECOVERING: frozenset(
        {
            CastState.STREAMING,
            CastState.DEGRADED,
            CastState.RECONNECTING,
            CastState.STOPPING,
            CastState.FAILED,
        }
    ),
    CastState.RECONNECTING: frozenset(
        {
            CastState.NEGOTIATING,
            CastState.STREAMING,
            CastState.STOPPING,
            CastState.FAILED,
        }
    ),
    CastState.STOPPING: frozenset({CastState.IDLE, CastState.FAILED}),
    CastState.FAILED: frozenset({CastState.IDLE, CastState.CHECKING_CAPABILITIES}),
}


def advance(current: CastState, target: CastState) -> CastState:
    """Aplica uma transição declarada; recusa qualquer atalho não previsto."""

    if target not in _TRANSITIONS[current]:
        raise SteamZeroError(
            "E-CAST-STATE-INVALID",
            detail=f"transição recusada: {current.value} -> {target.value}",
        )
    return target


def is_terminal_for_capture(state: CastState) -> bool:
    """True quando nenhuma captura pode continuar ativa naquele estado."""

    return state in {CastState.IDLE, CastState.FAILED}


# --- Perfis de qualidade ---------------------------------------------------
@dataclass(frozen=True)
class QualityProfile:
    profile_id: str
    width: int
    height: int
    frame_rate: int
    bitrate_kbps: int
    floor_bitrate_kbps: int
    video_codec: str = MANDATORY_VIDEO_CODEC
    audio_codec: str = MANDATORY_AUDIO_CODEC


_PERFORMANCE = QualityProfile("performance", 1280, 720, 60, 8000, 4000)
_BALANCED = QualityProfile("balanced", 1920, 1080, 60, 15000, 6000)
_QUALITY = QualityProfile("quality", 2560, 1440, 60, 32000, 10000)

PROFILES: dict[str, QualityProfile] = {
    _PERFORMANCE.profile_id: _PERFORMANCE,
    _BALANCED.profile_id: _BALANCED,
    _QUALITY.profile_id: _QUALITY,
}

# Degraus de resolução da escada de degradação (spec §13), do maior ao menor.
_RESOLUTION_LADDER = ((2560, 1440), (1920, 1080), (1280, 720), (960, 540))
_FLOOR_RESOLUTION = _RESOLUTION_LADDER[-1]
_FLOOR_FRAME_RATE = 30


def profile_for(profile_id: str) -> QualityProfile:
    profile = PROFILES.get(profile_id)
    if profile is None:
        raise SteamZeroError(
            "E-API-SCHEMA", detail=f"perfil de qualidade desconhecido: {profile_id}"
        )
    return profile


# --- Capacidade observada -------------------------------------------------
_PROTOCOL_MODES: dict[CastProtocol, frozenset[CastMode]] = {
    CastProtocol.GAME_STREAM: frozenset({CastMode.GAME, CastMode.GAME_WINDOW, CastMode.MIRROR}),
    CastProtocol.WEB_RECEIVER: frozenset({CastMode.GAME, CastMode.GAME_WINDOW, CastMode.MIRROR}),
    CastProtocol.STEAM_REMOTE_PLAY: frozenset({CastMode.GAME}),
    CastProtocol.SCREEN_MIRROR: frozenset({CastMode.MIRROR}),
    CastProtocol.MEDIA_CAST: frozenset({CastMode.MEDIA}),
}

# Ordem de preferência por modo — é daqui que sai a cadeia de fallback.
_MODE_PREFERENCE: dict[CastMode, tuple[CastProtocol, ...]] = {
    # Espelhamento não aparece aqui: quando nenhum receptor prova o modo Jogo,
    # a queda é de MODO (Jogo -> Espelhar), decidida em select_target.
    CastMode.GAME: (CastProtocol.GAME_STREAM, CastProtocol.WEB_RECEIVER, CastProtocol.STEAM_REMOTE_PLAY),
    CastMode.GAME_WINDOW: (CastProtocol.GAME_STREAM, CastProtocol.WEB_RECEIVER),
    CastMode.MIRROR: (CastProtocol.SCREEN_MIRROR, CastProtocol.GAME_STREAM, CastProtocol.WEB_RECEIVER),
    CastMode.MEDIA: (CastProtocol.MEDIA_CAST,),
}

_AUTOMATIC_ORDER = (CastMode.GAME, CastMode.MIRROR, CastMode.MEDIA)

_QUALITY_RANK = {
    LinkQuality.EXCELLENT: 3,
    LinkQuality.GOOD: 2,
    LinkQuality.LIMITED: 1,
    LinkQuality.UNKNOWN: 0,
}


@dataclass(frozen=True)
class ResolvedReceiver:
    """Receptor com modos que ele PROVOU suportar e o motivo de cada recusa."""

    receiver_id: str
    display_name: str
    protocol: CastProtocol
    transport: str
    paired: bool
    supported_modes: tuple[CastMode, ...]
    estimated_quality: LinkQuality
    blocked_reason: str
    capabilities: CastCapabilities

    def supports(self, mode: CastMode) -> bool:
        return mode in self.supported_modes


def _known_protocol(value: str) -> CastProtocol | None:
    for protocol in CastProtocol:
        if protocol.value == value:
            return protocol
    return None


def _mode_is_observed(mode: CastMode, caps: CastCapabilities) -> bool:
    if mode is CastMode.MEDIA:
        return True
    if mode is CastMode.GAME_WINDOW:
        return caps.application_window
    if mode is CastMode.MIRROR:
        return caps.full_screen
    return caps.full_screen or caps.application_window


def _estimate_quality(caps: CastCapabilities, transport: str) -> LinkQuality:
    """Estimativa a partir de evidência: pixels, quadros e transporte medidos."""

    if caps.max_width <= 0 or caps.max_frame_rate <= 0:
        return LinkQuality.UNKNOWN
    if transport not in {"wired", "lan", "wifi-direct"}:
        return LinkQuality.UNKNOWN
    if caps.max_width >= 1920 and caps.max_frame_rate >= 60 and transport in {"wired", "lan"}:
        return LinkQuality.EXCELLENT
    if caps.max_width >= 1280 and caps.max_frame_rate >= 60:
        return LinkQuality.GOOD
    return LinkQuality.LIMITED


def resolve_receiver(descriptor: ReceiverDescriptor) -> ResolvedReceiver:
    """Traduz o anúncio de um provedor em capacidade verificável.

    Um receptor sem codec comum, sem app receptor exigido ou sem nenhuma
    capacidade observada sai daqui com ``supported_modes`` vazio e um
    ``blocked_reason`` que a UI transforma em ação concreta — nunca em
    "erro desconhecido" (spec §6.3).
    """

    protocol = _known_protocol(descriptor.protocol)
    if protocol is None:
        return ResolvedReceiver(
            receiver_id=descriptor.receiver_id,
            display_name=descriptor.display_name,
            protocol=CastProtocol.SCREEN_MIRROR,
            transport=descriptor.transport,
            paired=descriptor.paired,
            supported_modes=(),
            estimated_quality=LinkQuality.UNKNOWN,
            blocked_reason="protocol-unknown",
            capabilities=descriptor.capabilities,
        )

    caps = descriptor.capabilities
    blocked = ""
    if caps.requires_receiver_app and not caps.receiver_app_present:
        blocked = "receiver-app-required"
    elif protocol is not CastProtocol.MEDIA_CAST and MANDATORY_VIDEO_CODEC not in caps.video_codecs:
        blocked = "codec-unavailable"
    elif not caps.max_width or not caps.max_frame_rate:
        blocked = "capabilities-unknown"

    modes: tuple[CastMode, ...] = ()
    if not blocked:
        modes = tuple(
            mode
            for mode in CastMode
            if mode is not CastMode.AUTOMATIC
            and mode in _PROTOCOL_MODES[protocol]
            and _mode_is_observed(mode, caps)
        )
        if not modes:
            blocked = "no-supported-mode"

    return ResolvedReceiver(
        receiver_id=descriptor.receiver_id,
        display_name=descriptor.display_name,
        protocol=protocol,
        transport=descriptor.transport,
        paired=descriptor.paired,
        supported_modes=modes,
        estimated_quality=_estimate_quality(caps, descriptor.transport),
        blocked_reason=blocked,
        capabilities=caps,
    )


# --- Seleção de um toque --------------------------------------------------
@dataclass(frozen=True)
class Selection:
    """Alvo escolhido mais a cadeia de fallback já ordenada."""

    receiver: ResolvedReceiver
    mode: CastMode
    fallback_ids: tuple[str, ...]


def _rank(receiver: ResolvedReceiver, mode: CastMode) -> tuple[int, int, int, str]:
    preference = _MODE_PREFERENCE[mode]
    return (
        preference.index(receiver.protocol),
        -_QUALITY_RANK[receiver.estimated_quality],
        0 if receiver.paired else 1,
        receiver.receiver_id,
    )


def _candidates(receivers: tuple[ResolvedReceiver, ...], mode: CastMode) -> list[ResolvedReceiver]:
    eligible = [
        receiver
        for receiver in receivers
        if receiver.supports(mode) and receiver.protocol in _MODE_PREFERENCE[mode]
    ]
    return sorted(eligible, key=lambda receiver: _rank(receiver, mode))


def select_target(mode: CastMode, receivers: tuple[ResolvedReceiver, ...]) -> Selection:
    """O "um toque": resolve modo efetivo, melhor alvo e ordem de fallback."""

    modes = _AUTOMATIC_ORDER if mode is CastMode.AUTOMATIC else (mode,)
    for effective in modes:
        ordered = _candidates(receivers, effective)
        if ordered:
            return Selection(
                receiver=ordered[0],
                mode=effective,
                fallback_ids=tuple(item.receiver_id for item in ordered[1:]),
            )
    raise SteamZeroError(
        "E-CAST-NO-RECEIVER",
        detail=f"nenhum receptor comprovou suporte ao modo {mode.value}",
    )


# --- Negociação -----------------------------------------------------------
@dataclass(frozen=True)
class NegotiatedStream:
    profile_id: str
    width: int
    height: int
    frame_rate: int
    bitrate_kbps: int
    video_codec: str
    audio_codec: str
    hardware_encoder: bool
    input_back_channel: bool


def _common_codec(mandatory: str, local: tuple[str, ...], remote: tuple[str, ...]) -> str:
    shared = [codec for codec in local if codec in remote]
    if mandatory in shared:
        return mandatory
    if not shared:
        raise SteamZeroError(
            "E-CAST-RECEIVER-INCOMPATIBLE",
            detail=f"sem codec comum; {mandatory} é o piso exigido",
        )
    return shared[0]


def negotiate(
    profile: QualityProfile,
    receiver: ResolvedReceiver,
    local: CastCapabilities,
    *,
    mode: CastMode,
    input_back_channel: bool = False,
) -> NegotiatedStream:
    """Rebaixa o perfil ao menor teto observado dos dois lados.

    Nunca sobe: um receptor que não provou 1080p60 não recebe 1080p60 só porque
    o perfil pedia. Codec mais moderno é negociado, jamais presumido.
    """

    if receiver.blocked_reason:
        raise SteamZeroError(
            "E-CAST-RECEIVER-INCOMPATIBLE",
            detail=f"receptor bloqueado: {receiver.blocked_reason}",
        )
    if not receiver.supports(mode):
        raise SteamZeroError(
            "E-CAST-RECEIVER-INCOMPATIBLE",
            detail=f"receptor não comprovou o modo {mode.value}",
        )

    remote = receiver.capabilities
    width = min(profile.width, remote.max_width or profile.width, local.max_width or profile.width)
    height = min(
        profile.height, remote.max_height or profile.height, local.max_height or profile.height
    )
    frame_rate = min(
        profile.frame_rate,
        remote.max_frame_rate or profile.frame_rate,
        local.max_frame_rate or profile.frame_rate,
    )
    video = _common_codec(profile.video_codec, local.video_codecs, remote.video_codecs)
    audio = _common_codec(profile.audio_codec, local.audio_codecs, remote.audio_codecs)

    # Menos pixels/quadros do que o perfil previa => menos bits, proporcional.
    planned_pixels = profile.width * profile.height * profile.frame_rate
    actual_pixels = width * height * frame_rate
    bitrate = profile.bitrate_kbps
    if actual_pixels < planned_pixels:
        bitrate = max(profile.floor_bitrate_kbps, (bitrate * actual_pixels) // planned_pixels)

    return NegotiatedStream(
        profile_id=profile.profile_id,
        width=width,
        height=height,
        frame_rate=frame_rate,
        bitrate_kbps=bitrate,
        video_codec=video,
        audio_codec=audio,
        hardware_encoder=local.hardware_encoder,
        input_back_channel=input_back_channel and remote.input_back_channel,
    )


# --- Qualidade adaptativa -------------------------------------------------
@dataclass(frozen=True)
class QualityDecision:
    action: QualityAction
    stream: NegotiatedStream
    request_keyframe: bool
    degraded: bool
    exhausted: bool


def _reduce_resolution(stream: NegotiatedStream) -> NegotiatedStream | None:
    current = (stream.width, stream.height)
    for index, step in enumerate(_RESOLUTION_LADDER):
        if step == current and index + 1 < len(_RESOLUTION_LADDER):
            nxt = _RESOLUTION_LADDER[index + 1]
            return replace(stream, width=nxt[0], height=nxt[1])
    if current not in _RESOLUTION_LADDER and stream.width > _FLOOR_RESOLUTION[0]:
        # Resolução fora da escada (negociada pelo receptor): cai para o piso.
        return replace(stream, width=_FLOOR_RESOLUTION[0], height=_FLOOR_RESOLUTION[1])
    return None


def plan_quality(
    stream: NegotiatedStream, profile: QualityProfile, sample: LinkSample
) -> QualityDecision:
    """Escada de degradação: perder qualidade sempre antes de perder a sessão.

    Quando não há mais o que reduzir, devolve ``exhausted`` em vez de derrubar:
    quem decide reconectar é a máquina de estados, não o controle de bitrate.
    """

    severe = sample.packet_loss_pct > 3.0 or sample.decoder_queue_frames >= 4
    moderate = sample.packet_loss_pct > 1.0 or sample.rtt_ms > 60
    queue_growing = sample.decoder_queue_frames >= 2

    if severe:
        smaller = _reduce_resolution(stream)
        if smaller is not None:
            return QualityDecision(
                action=QualityAction.REDUCE_RESOLUTION,
                stream=smaller,
                request_keyframe=True,
                degraded=True,
                exhausted=False,
            )
        if stream.frame_rate > _FLOOR_FRAME_RATE:
            return QualityDecision(
                action=QualityAction.REDUCE_FRAME_RATE,
                stream=replace(stream, frame_rate=_FLOOR_FRAME_RATE),
                request_keyframe=True,
                degraded=True,
                exhausted=False,
            )
        return QualityDecision(
            action=QualityAction.HOLD,
            stream=stream,
            request_keyframe=True,
            degraded=True,
            exhausted=True,
        )

    if moderate or queue_growing:
        floor = profile.floor_bitrate_kbps
        reduced = max(floor, (stream.bitrate_kbps * 3) // 4)
        exhausted = reduced >= stream.bitrate_kbps
        return QualityDecision(
            action=QualityAction.HOLD if exhausted else QualityAction.REDUCE_BITRATE,
            stream=replace(stream, bitrate_kbps=reduced),
            request_keyframe=queue_growing,
            degraded=True,
            exhausted=exhausted,
        )

    stable = (
        sample.packet_loss_pct < 0.5 and sample.rtt_ms < 30 and sample.decoder_queue_frames <= 1
    )
    if stable and stream.bitrate_kbps < profile.bitrate_kbps:
        raised = min(profile.bitrate_kbps, (stream.bitrate_kbps * 5) // 4)
        return QualityDecision(
            action=QualityAction.RAISE,
            stream=replace(stream, bitrate_kbps=raised),
            request_keyframe=False,
            degraded=False,
            exhausted=False,
        )
    return QualityDecision(
        action=QualityAction.HOLD,
        stream=stream,
        request_keyframe=False,
        degraded=False,
        exhausted=False,
    )


# --- Recuperação ----------------------------------------------------------
@dataclass(frozen=True)
class RecoveryPlan:
    fault: FaultKind
    actions: tuple[RecoveryAction, ...]
    target_state: CastState
    keeps_session: bool
    error_code: str


_RECOVERY: dict[FaultKind, RecoveryPlan] = {
    FaultKind.ENCODER_LOST: RecoveryPlan(
        FaultKind.ENCODER_LOST,
        (
            RecoveryAction.PAUSE_SEND,
            RecoveryAction.REBUILD_ENCODER,
            RecoveryAction.REQUEST_KEYFRAME,
            RecoveryAction.RESUME_SEND,
        ),
        CastState.RECOVERING,
        True,
        "",
    ),
    FaultKind.RESOLUTION_CHANGED: RecoveryPlan(
        FaultKind.RESOLUTION_CHANGED,
        (RecoveryAction.RENEGOTIATE_STREAM, RecoveryAction.REQUEST_KEYFRAME),
        CastState.RECOVERING,
        True,
        "",
    ),
    FaultKind.AUDIO_DEVICE_CHANGED: RecoveryPlan(
        FaultKind.AUDIO_DEVICE_CHANGED,
        (RecoveryAction.RESTART_AUDIO, RecoveryAction.RESYNC_CLOCK),
        CastState.RECOVERING,
        True,
        "",
    ),
    FaultKind.LINK_LOST: RecoveryPlan(
        FaultKind.LINK_LOST,
        (RecoveryAction.BACKOFF_RECONNECT, RecoveryAction.REQUEST_KEYFRAME),
        CastState.RECONNECTING,
        True,
        "",
    ),
    FaultKind.RECEIVER_RESTARTED: RecoveryPlan(
        FaultKind.RECEIVER_RESTARTED,
        (RecoveryAction.BACKOFF_RECONNECT, RecoveryAction.REQUEST_KEYFRAME),
        CastState.RECONNECTING,
        True,
        "",
    ),
    FaultKind.HOST_SUSPENDED: RecoveryPlan(
        FaultKind.HOST_SUSPENDED,
        (
            RecoveryAction.PAUSE_SEND,
            RecoveryAction.BACKOFF_RECONNECT,
            RecoveryAction.REQUEST_KEYFRAME,
        ),
        CastState.RECONNECTING,
        True,
        "",
    ),
    FaultKind.GAME_EXITED: RecoveryPlan(
        FaultKind.GAME_EXITED,
        (RecoveryAction.SWITCH_SOURCE_TO_LAUNCHER, RecoveryAction.REQUEST_KEYFRAME),
        CastState.RECOVERING,
        True,
        "",
    ),
    # Privacidade e DRM não se recuperam sozinhos: param, com causa registrada.
    FaultKind.CONSENT_REVOKED: RecoveryPlan(
        FaultKind.CONSENT_REVOKED,
        (RecoveryAction.STOP_CAPTURE,),
        CastState.STOPPING,
        False,
        "E-CAST-CONSENT-REQUIRED",
    ),
    FaultKind.PROTECTED_CONTENT: RecoveryPlan(
        FaultKind.PROTECTED_CONTENT,
        (RecoveryAction.PAUSE_SEND, RecoveryAction.SHOW_PROTECTED_NOTICE),
        CastState.DEGRADED,
        True,
        "E-CAST-PROTECTED-CONTENT",
    ),
}


def plan_recovery(fault: FaultKind) -> RecoveryPlan:
    return _RECOVERY[fault]


def reconnect_delay(attempt: int) -> int:
    """Atraso do degrau ``attempt`` (0-based). Esgotado => sessão falha."""

    if attempt < 0:
        raise SteamZeroError("E-API-SCHEMA", detail="tentativa de reconexão negativa")
    if attempt >= len(RECONNECT_DELAYS_SECONDS):
        raise SteamZeroError(
            "E-CAST-LINK-LOST",
            detail=f"enlace perdido após {len(RECONNECT_DELAYS_SECONDS)} tentativas",
        )
    return RECONNECT_DELAYS_SECONDS[attempt]


# --- Consentimento e conteúdo protegido -----------------------------------
_CONSENT_SCOPES = {
    CastMode.GAME: frozenset({"monitor", "window", "virtual"}),
    CastMode.GAME_WINDOW: frozenset({"window", "virtual"}),
    CastMode.MIRROR: frozenset({"monitor", "virtual"}),
    CastMode.MEDIA: frozenset({"monitor", "window", "virtual", "none"}),
}


def guard_consent(consent: CaptureConsent, mode: CastMode) -> CaptureConsent:
    """Sem autorização do portal para o escopo pedido, não há sessão."""

    if mode is CastMode.MEDIA and not consent.granted:
        # Mídia não captura a tela: o receptor busca o conteúdo por conta dele.
        return consent
    if not consent.granted:
        raise SteamZeroError("E-CAST-CONSENT-REQUIRED", detail="captura sem autorização do usuário")
    if consent.scope not in _CONSENT_SCOPES[mode]:
        raise SteamZeroError(
            "E-CAST-CONSENT-REQUIRED",
            detail=f"escopo {consent.scope} não autoriza o modo {mode.value}",
        )
    return consent


def guard_protected_content(flagged: bool) -> None:
    """Conteúdo protegido interrompe o envio; nunca é contornado (spec §18)."""

    if flagged:
        raise SteamZeroError(
            "E-CAST-PROTECTED-CONTENT",
            detail="conteúdo protegido não pode ser compartilhado",
        )


# --- Sessão e contrato público -------------------------------------------
def receiver_digest(receiver_id: str) -> str:
    """Identidade anônima e estável do receptor para log e telemetria."""

    return crypto.digest_bytes(receiver_id.encode("utf-8")).hexdigest[:12]


@dataclass(frozen=True)
class CastSession:
    """Estado publicável de uma sessão. Não guarda nome, endereço nem PIN."""

    protocol: CastProtocol
    mode: CastMode
    state: CastState
    transport: str
    digest: str
    estimated_quality: LinkQuality
    stream: NegotiatedStream
    consent: CaptureConsent
    degraded: bool = False
    attempt: int = 0
    quality_exhausted: bool = False
    duration_seconds: int = 0

    @classmethod
    def opened(
        cls,
        selection: Selection,
        stream: NegotiatedStream,
        consent: CaptureConsent,
    ) -> CastSession:
        return cls(
            protocol=selection.receiver.protocol,
            mode=selection.mode,
            state=CastState.NEGOTIATING,
            transport=selection.receiver.transport,
            digest=receiver_digest(selection.receiver.receiver_id),
            estimated_quality=selection.receiver.estimated_quality,
            stream=stream,
            consent=guard_consent(consent, selection.mode),
        )

    def moved_to(self, target: CastState) -> CastSession:
        return replace(self, state=advance(self.state, target))

    def with_quality(self, decision: QualityDecision) -> CastSession:
        return replace(
            self,
            stream=decision.stream,
            degraded=decision.degraded,
            quality_exhausted=decision.exhausted,
        )

    def public(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schemaVersion": 1,
            "protocol": self.protocol.value,
            "mode": self.mode.value,
            "state": self.state.value,
            "transport": self.transport,
            "receiverDigest": self.digest,
            "estimatedQuality": self.estimated_quality.value,
            "stream": {
                "profileId": self.stream.profile_id,
                "width": self.stream.width,
                "height": self.stream.height,
                "frameRate": self.stream.frame_rate,
                "bitrateKbps": self.stream.bitrate_kbps,
                "videoCodec": self.stream.video_codec,
                "audioCodec": self.stream.audio_codec,
                "hardwareEncoder": self.stream.hardware_encoder,
                "inputBackChannel": self.stream.input_back_channel,
            },
            "consent": {"granted": self.consent.granted, "scope": self.consent.scope},
            "resilience": {
                "degraded": self.degraded,
                "attempt": self.attempt,
                "qualityExhausted": self.quality_exhausted,
                "reconnectDelaysSeconds": list(RECONNECT_DELAYS_SECONDS),
            },
            "durationSeconds": self.duration_seconds,
        }
        contracts.validate(payload, "screen-cast-v1.schema.json")
        return payload
