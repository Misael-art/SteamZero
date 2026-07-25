# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import pytest

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError
from steamzero.domain import screencast as sc
from steamzero.ports import CaptureConsent, CastCapabilities, LinkSample, ReceiverDescriptor

_FULL = CastCapabilities(
    full_screen=True,
    application_window=True,
    system_audio=True,
    input_back_channel=True,
    max_width=1920,
    max_height=1080,
    max_frame_rate=60,
    video_codecs=("h264", "hevc"),
    audio_codecs=("opus",),
)
_LOCAL = CastCapabilities(
    full_screen=True,
    application_window=True,
    system_audio=True,
    input_back_channel=True,
    hardware_encoder=True,
    max_width=2560,
    max_height=1440,
    max_frame_rate=60,
    video_codecs=("h264", "hevc"),
    audio_codecs=("opus",),
)


def _descriptor(
    receiver_id: str = "tv-sala",
    *,
    protocol: str = "game-stream",
    transport: str = "lan",
    paired: bool = True,
    capabilities: CastCapabilities = _FULL,
) -> ReceiverDescriptor:
    return ReceiverDescriptor(
        receiver_id=receiver_id,
        display_name="TV da Sala",
        protocol=protocol,
        address="192.168.1.20:47989",
        transport=transport,
        paired=paired,
        capabilities=capabilities,
    )


def _streaming_session() -> tuple[sc.CastSession, sc.QualityProfile]:
    receiver = sc.resolve_receiver(_descriptor())
    selection = sc.select_target(sc.CastMode.GAME, (receiver,))
    profile = sc.profile_for("balanced")
    stream = sc.negotiate(profile, selection.receiver, _LOCAL, mode=selection.mode)
    session = sc.CastSession.opened(
        selection, stream, CaptureConsent(granted=True, scope="monitor", audio=True)
    )
    return session.moved_to(sc.CastState.STREAMING), profile


# --- Máquina de estados: nenhum beco sem saída ----------------------------
def test_every_state_can_reach_idle_and_has_an_exit() -> None:
    for state in sc.CastState:
        assert sc._TRANSITIONS[state], f"{state.value} é beco sem saída"

    reachable = {sc.CastState.IDLE}
    changed = True
    while changed:
        changed = False
        for state, targets in sc._TRANSITIONS.items():
            if state not in reachable and targets & reachable:
                reachable.add(state)
                changed = True
    assert reachable == set(sc.CastState), "há estado que não consegue voltar a idle"


def test_streaming_never_shortcuts_to_idle() -> None:
    for state in (sc.CastState.STREAMING, sc.CastState.DEGRADED, sc.CastState.RECOVERING):
        assert sc.CastState.IDLE not in sc._TRANSITIONS[state]
        with pytest.raises(SteamZeroError, match="transição recusada"):
            sc.advance(state, sc.CastState.IDLE)


def test_advance_accepts_declared_transition() -> None:
    assert sc.advance(sc.CastState.STREAMING, sc.CastState.DEGRADED) is sc.CastState.DEGRADED


def test_capture_is_terminal_only_when_session_is_over() -> None:
    assert sc.is_terminal_for_capture(sc.CastState.IDLE)
    assert sc.is_terminal_for_capture(sc.CastState.FAILED)
    assert not sc.is_terminal_for_capture(sc.CastState.DEGRADED)


# --- Capacidade observada, nunca presumida --------------------------------
def test_resolved_receiver_publishes_only_proven_modes() -> None:
    resolved = sc.resolve_receiver(_descriptor())
    assert resolved.supported_modes == (
        sc.CastMode.GAME,
        sc.CastMode.GAME_WINDOW,
        sc.CastMode.MIRROR,
    )
    assert resolved.estimated_quality is sc.LinkQuality.EXCELLENT
    assert resolved.blocked_reason == ""


@pytest.mark.parametrize(
    "capabilities,reason",
    [
        (
            CastCapabilities(
                full_screen=True,
                requires_receiver_app=True,
                max_width=1920,
                max_frame_rate=60,
                video_codecs=("h264",),
            ),
            "receiver-app-required",
        ),
        (
            CastCapabilities(
                full_screen=True, max_width=1920, max_frame_rate=60, video_codecs=("hevc",)
            ),
            "codec-unavailable",
        ),
        (CastCapabilities(full_screen=True, video_codecs=("h264",)), "capabilities-unknown"),
        (
            CastCapabilities(max_width=1920, max_frame_rate=60, video_codecs=("h264",)),
            "no-supported-mode",
        ),
    ],
)
def test_blocked_receiver_states_a_concrete_reason(
    capabilities: CastCapabilities, reason: str
) -> None:
    resolved = sc.resolve_receiver(_descriptor(capabilities=capabilities))
    assert resolved.supported_modes == ()
    assert resolved.blocked_reason == reason


def test_unknown_protocol_is_refused_not_guessed() -> None:
    resolved = sc.resolve_receiver(_descriptor(protocol="smart-mirror-2015"))
    assert resolved.blocked_reason == "protocol-unknown"
    assert resolved.supported_modes == ()


def test_quality_estimate_ignores_identity_and_needs_evidence() -> None:
    unknown_transport = sc.resolve_receiver(_descriptor(transport="unknown"))
    assert unknown_transport.estimated_quality is sc.LinkQuality.UNKNOWN

    modest = sc.resolve_receiver(
        _descriptor(
            capabilities=CastCapabilities(
                full_screen=True,
                max_width=1280,
                max_height=720,
                max_frame_rate=30,
                video_codecs=("h264",),
                audio_codecs=("opus",),
            )
        )
    )
    assert modest.estimated_quality is sc.LinkQuality.LIMITED


# --- Seleção de um toque e cadeia de fallback ----------------------------
def test_one_touch_prefers_low_latency_and_keeps_fallback_order() -> None:
    game = sc.resolve_receiver(_descriptor("deck-tv"))
    other_game = sc.resolve_receiver(_descriptor("quarto-tv"))
    steam = sc.resolve_receiver(_descriptor("steam-tv", protocol="steam-remote-play"))
    mirror = sc.resolve_receiver(_descriptor("miracast-tv", protocol="screen-mirror"))

    selection = sc.select_target(sc.CastMode.AUTOMATIC, (mirror, steam, other_game, game))

    assert selection.mode is sc.CastMode.GAME
    assert selection.receiver.receiver_id == "deck-tv"
    # Espelhamento não entra na cadeia do modo Jogo: ele é queda de modo, não de alvo.
    assert selection.fallback_ids == ("quarto-tv", "steam-tv")


def test_mirror_only_receiver_degrades_the_mode_not_the_promise() -> None:
    mirror = sc.resolve_receiver(_descriptor("miracast-tv", protocol="screen-mirror"))
    game = sc.resolve_receiver(_descriptor("deck-tv"))

    with pytest.raises(SteamZeroError, match="nenhum receptor"):
        sc.select_target(sc.CastMode.GAME, (mirror,))

    # No modo Espelhar, o motor de jogo é alternativa válida do espelhamento.
    selection = sc.select_target(sc.CastMode.MIRROR, (game, mirror))
    assert selection.receiver.receiver_id == "miracast-tv"
    assert selection.fallback_ids == ("deck-tv",)


def test_automatic_falls_back_to_mirror_then_media() -> None:
    mirror = sc.resolve_receiver(_descriptor("miracast-tv", protocol="screen-mirror"))
    assert sc.select_target(sc.CastMode.AUTOMATIC, (mirror,)).mode is sc.CastMode.MIRROR

    media = sc.resolve_receiver(
        _descriptor(
            "cast-antigo",
            protocol="media-cast",
            capabilities=CastCapabilities(max_width=1920, max_frame_rate=60),
        )
    )
    assert sc.select_target(sc.CastMode.AUTOMATIC, (media,)).mode is sc.CastMode.MEDIA


def test_paired_and_better_link_win_between_equals() -> None:
    weak = sc.resolve_receiver(
        _descriptor(
            "tv-fraca",
            capabilities=CastCapabilities(
                full_screen=True,
                max_width=1280,
                max_height=720,
                max_frame_rate=60,
                video_codecs=("h264",),
                audio_codecs=("opus",),
            ),
        )
    )
    strong = sc.resolve_receiver(_descriptor("tv-forte"))
    assert sc.select_target(sc.CastMode.GAME, (weak, strong)).receiver.receiver_id == "tv-forte"

    unpaired = sc.resolve_receiver(_descriptor("tv-nova", paired=False))
    paired = sc.resolve_receiver(_descriptor("tv-conhecida"))
    assert sc.select_target(sc.CastMode.GAME, (unpaired, paired)).receiver.receiver_id == (
        "tv-conhecida"
    )


def test_no_receiver_is_an_actionable_error() -> None:
    media_only = sc.resolve_receiver(
        _descriptor(
            protocol="media-cast",
            capabilities=CastCapabilities(max_width=1920, max_frame_rate=60),
        )
    )
    with pytest.raises(SteamZeroError, match="nenhum receptor") as excinfo:
        sc.select_target(sc.CastMode.GAME, (media_only,))
    assert excinfo.value.code == "E-CAST-NO-RECEIVER"


# --- Negociação: rebaixa, nunca promove ----------------------------------
def test_negotiation_clamps_to_the_smallest_observed_ceiling() -> None:
    receiver = sc.resolve_receiver(_descriptor())
    stream = sc.negotiate(sc.profile_for("quality"), receiver, _LOCAL, mode=sc.CastMode.GAME)

    assert (stream.width, stream.height, stream.frame_rate) == (1920, 1080, 60)
    assert stream.bitrate_kbps < sc.profile_for("quality").bitrate_kbps
    assert stream.video_codec == "h264"
    assert stream.hardware_encoder is True


def test_negotiation_uses_an_alternate_codec_only_when_the_floor_is_absent() -> None:
    aac_only = CastCapabilities(
        full_screen=True,
        max_width=1920,
        max_height=1080,
        max_frame_rate=60,
        video_codecs=("h264",),
        audio_codecs=("aac",),
    )
    local = CastCapabilities(
        full_screen=True,
        hardware_encoder=True,
        max_width=1920,
        max_height=1080,
        max_frame_rate=60,
        video_codecs=("h264",),
        audio_codecs=("opus", "aac"),
    )
    stream = sc.negotiate(
        sc.profile_for("balanced"),
        sc.resolve_receiver(_descriptor(capabilities=aac_only)),
        local,
        mode=sc.CastMode.GAME,
    )
    assert stream.audio_codec == "aac"
    assert stream.video_codec == sc.MANDATORY_VIDEO_CODEC


def test_negotiation_requires_a_common_codec() -> None:
    exotic = CastCapabilities(
        full_screen=True,
        max_width=1920,
        max_height=1080,
        max_frame_rate=60,
        video_codecs=("h264",),
        audio_codecs=("dts",),
    )
    receiver = sc.resolve_receiver(_descriptor(capabilities=exotic))
    with pytest.raises(SteamZeroError, match="codec comum") as excinfo:
        sc.negotiate(sc.profile_for("balanced"), receiver, _LOCAL, mode=sc.CastMode.GAME)
    assert excinfo.value.code == "E-CAST-RECEIVER-INCOMPATIBLE"


def test_negotiation_refuses_unproven_mode_and_blocked_receiver() -> None:
    mirror_only = sc.resolve_receiver(_descriptor(protocol="screen-mirror"))
    with pytest.raises(SteamZeroError, match="não comprovou o modo"):
        sc.negotiate(sc.profile_for("balanced"), mirror_only, _LOCAL, mode=sc.CastMode.GAME)

    blocked = sc.resolve_receiver(_descriptor(protocol="desconhecido"))
    with pytest.raises(SteamZeroError, match="bloqueado"):
        sc.negotiate(sc.profile_for("balanced"), blocked, _LOCAL, mode=sc.CastMode.MIRROR)


def test_input_back_channel_only_when_receiver_proved_it() -> None:
    silent = CastCapabilities(
        full_screen=True,
        max_width=1920,
        max_height=1080,
        max_frame_rate=60,
        video_codecs=("h264",),
        audio_codecs=("opus",),
    )
    receiver = sc.resolve_receiver(_descriptor(capabilities=silent))
    stream = sc.negotiate(
        sc.profile_for("balanced"),
        receiver,
        _LOCAL,
        mode=sc.CastMode.GAME,
        input_back_channel=True,
    )
    assert stream.input_back_channel is False


def test_unknown_quality_profile_is_refused() -> None:
    with pytest.raises(SteamZeroError, match="perfil de qualidade"):
        sc.profile_for("ultra")


# --- Qualidade cai antes da sessão ---------------------------------------
def test_moderate_loss_reduces_bitrate_before_anything_else() -> None:
    session, profile = _streaming_session()
    decision = sc.plan_quality(session.stream, profile, LinkSample(packet_loss_pct=2.0))

    assert decision.action is sc.QualityAction.REDUCE_BITRATE
    assert decision.stream.bitrate_kbps < session.stream.bitrate_kbps
    assert (decision.stream.width, decision.stream.frame_rate) == (
        session.stream.width,
        session.stream.frame_rate,
    )
    assert decision.degraded is True and decision.exhausted is False


def test_severe_loss_reduces_resolution_and_asks_keyframe() -> None:
    session, profile = _streaming_session()
    decision = sc.plan_quality(session.stream, profile, LinkSample(packet_loss_pct=6.0))

    assert decision.action is sc.QualityAction.REDUCE_RESOLUTION
    assert (decision.stream.width, decision.stream.height) == (1280, 720)
    assert decision.request_keyframe is True


def test_growing_decoder_queue_reduces_and_reseeds() -> None:
    session, profile = _streaming_session()
    decision = sc.plan_quality(session.stream, profile, LinkSample(decoder_queue_frames=2))

    assert decision.action is sc.QualityAction.REDUCE_BITRATE
    assert decision.request_keyframe is True


def test_degradation_ladder_bottoms_out_without_dropping_the_session() -> None:
    session, profile = _streaming_session()
    stream = session.stream
    seen: set[tuple[int, int, int]] = set()
    decision = sc.plan_quality(stream, profile, LinkSample(packet_loss_pct=9.0))
    for _ in range(10):
        stream = decision.stream
        seen.add((stream.width, stream.height, stream.frame_rate))
        decision = sc.plan_quality(stream, profile, LinkSample(packet_loss_pct=9.0))
        if decision.exhausted:
            break

    assert decision.exhausted is True
    assert decision.degraded is True
    assert (decision.stream.width, decision.stream.height) == sc._FLOOR_RESOLUTION
    assert decision.stream.frame_rate == sc._FLOOR_FRAME_RATE
    assert (1280, 720, 60) in seen, "a escada precisa passar por 720p antes do piso"


def test_stable_link_recovers_quality_up_to_the_profile_ceiling() -> None:
    session, profile = _streaming_session()
    reduced = sc.plan_quality(session.stream, profile, LinkSample(packet_loss_pct=2.0)).stream
    good = LinkSample(packet_loss_pct=0.0, rtt_ms=12, decoder_queue_frames=0)

    first = sc.plan_quality(reduced, profile, good)
    assert first.action is sc.QualityAction.RAISE
    assert first.degraded is False

    stream = first.stream
    for _ in range(10):
        decision = sc.plan_quality(stream, profile, good)
        stream = decision.stream
    assert stream.bitrate_kbps == profile.bitrate_kbps
    assert sc.plan_quality(stream, profile, good).action is sc.QualityAction.HOLD


def test_bitrate_floor_reports_exhaustion_instead_of_shrinking_forever() -> None:
    session, profile = _streaming_session()
    stream = session.stream
    for _ in range(20):
        stream = sc.plan_quality(stream, profile, LinkSample(rtt_ms=120)).stream
    decision = sc.plan_quality(stream, profile, LinkSample(rtt_ms=120))
    assert decision.stream.bitrate_kbps == profile.floor_bitrate_kbps
    assert decision.exhausted is True
    assert decision.action is sc.QualityAction.HOLD


def test_resolution_outside_the_ladder_falls_to_the_floor() -> None:
    session, profile = _streaming_session()
    odd = sc.NegotiatedStream(
        profile_id="balanced",
        width=1600,
        height=900,
        frame_rate=60,
        bitrate_kbps=session.stream.bitrate_kbps,
        video_codec="h264",
        audio_codec="opus",
        hardware_encoder=True,
        input_back_channel=False,
    )
    decision = sc.plan_quality(odd, profile, LinkSample(packet_loss_pct=9.0))
    assert (decision.stream.width, decision.stream.height) == sc._FLOOR_RESOLUTION


# --- Recuperação ---------------------------------------------------------
def test_every_fault_has_a_plan_that_leads_somewhere() -> None:
    for fault in sc.FaultKind:
        plan = sc.plan_recovery(fault)
        assert plan.actions, f"{fault.value} sem ação"
        assert plan.target_state is not sc.CastState.IDLE
        assert plan.target_state in sc._TRANSITIONS[sc.CastState.STREAMING] or (
            plan.target_state in sc._TRANSITIONS[sc.CastState.DEGRADED]
        )


def test_resolution_change_renegotiates_without_tearing_the_session_down() -> None:
    plan = sc.plan_recovery(sc.FaultKind.RESOLUTION_CHANGED)
    assert plan.keeps_session is True
    assert plan.target_state is sc.CastState.RECOVERING
    assert sc.RecoveryAction.RENEGOTIATE_STREAM in plan.actions


def test_audio_device_change_keeps_video_and_resyncs() -> None:
    plan = sc.plan_recovery(sc.FaultKind.AUDIO_DEVICE_CHANGED)
    assert plan.actions == (sc.RecoveryAction.RESTART_AUDIO, sc.RecoveryAction.RESYNC_CLOCK)
    assert plan.keeps_session is True


def test_encoder_loss_rebuilds_and_resumes() -> None:
    plan = sc.plan_recovery(sc.FaultKind.ENCODER_LOST)
    assert plan.actions[0] is sc.RecoveryAction.PAUSE_SEND
    assert plan.actions[-1] is sc.RecoveryAction.RESUME_SEND
    assert sc.RecoveryAction.REQUEST_KEYFRAME in plan.actions


def test_consent_revocation_stops_and_never_auto_resumes() -> None:
    plan = sc.plan_recovery(sc.FaultKind.CONSENT_REVOKED)
    assert plan.actions == (sc.RecoveryAction.STOP_CAPTURE,)
    assert plan.keeps_session is False
    assert plan.target_state is sc.CastState.STOPPING
    assert plan.error_code == "E-CAST-CONSENT-REQUIRED"


def test_protected_content_pauses_and_explains_without_bypassing() -> None:
    plan = sc.plan_recovery(sc.FaultKind.PROTECTED_CONTENT)
    assert plan.actions == (
        sc.RecoveryAction.PAUSE_SEND,
        sc.RecoveryAction.SHOW_PROTECTED_NOTICE,
    )
    assert plan.error_code == "E-CAST-PROTECTED-CONTENT"

    sc.guard_protected_content(False)
    with pytest.raises(SteamZeroError, match="protegido") as excinfo:
        sc.guard_protected_content(True)
    assert excinfo.value.code == "E-CAST-PROTECTED-CONTENT"


def test_reconnect_backoff_is_progressive_then_gives_up_with_a_reason() -> None:
    assert [sc.reconnect_delay(attempt) for attempt in range(5)] == [0, 1, 2, 4, 8]
    with pytest.raises(SteamZeroError, match="enlace perdido") as excinfo:
        sc.reconnect_delay(5)
    assert excinfo.value.code == "E-CAST-LINK-LOST"
    with pytest.raises(SteamZeroError, match="negativa"):
        sc.reconnect_delay(-1)


# --- Consentimento ------------------------------------------------------
def test_capture_without_consent_is_refused() -> None:
    with pytest.raises(SteamZeroError, match="autorização") as excinfo:
        sc.guard_consent(CaptureConsent(), sc.CastMode.GAME)
    assert excinfo.value.code == "E-CAST-CONSENT-REQUIRED"


def test_window_scope_does_not_authorize_full_screen_mirror() -> None:
    with pytest.raises(SteamZeroError, match="escopo"):
        sc.guard_consent(CaptureConsent(granted=True, scope="window"), sc.CastMode.MIRROR)
    assert (
        sc.guard_consent(
            CaptureConsent(granted=True, scope="window"), sc.CastMode.GAME_WINDOW
        ).scope
        == "window"
    )


def test_media_mode_needs_no_capture_consent() -> None:
    assert sc.guard_consent(CaptureConsent(), sc.CastMode.MEDIA).granted is False


# --- Contrato público: privacidade por construção -----------------------
def test_public_session_validates_and_hides_identity() -> None:
    session, _ = _streaming_session()
    payload = session.public()
    contracts.validate(payload, "screen-cast-v1.schema.json")

    rendered = str(payload)
    assert "TV da Sala" not in rendered
    assert "192.168.1.20" not in rendered
    assert "tv-sala" not in rendered
    assert payload["receiverDigest"] == sc.receiver_digest("tv-sala")
    assert payload["state"] == "streaming"
    assert payload["resilience"] == {
        "degraded": False,
        "attempt": 0,
        "qualityExhausted": False,
        "reconnectDelaysSeconds": [0, 1, 2, 4, 8],
    }


def test_session_transitions_and_quality_are_immutable_updates() -> None:
    session, profile = _streaming_session()
    decision = sc.plan_quality(session.stream, profile, LinkSample(packet_loss_pct=2.0))

    degraded = session.with_quality(decision).moved_to(sc.CastState.DEGRADED)

    assert session.state is sc.CastState.STREAMING
    assert session.degraded is False
    assert degraded.state is sc.CastState.DEGRADED
    assert degraded.degraded is True
    assert degraded.stream.bitrate_kbps < session.stream.bitrate_kbps
    contracts.validate(degraded.public(), "screen-cast-v1.schema.json")


def test_session_cannot_open_without_consent() -> None:
    receiver = sc.resolve_receiver(_descriptor())
    selection = sc.select_target(sc.CastMode.GAME, (receiver,))
    stream = sc.negotiate(sc.profile_for("balanced"), receiver, _LOCAL, mode=sc.CastMode.GAME)
    with pytest.raises(SteamZeroError, match="autorização"):
        sc.CastSession.opened(selection, stream, CaptureConsent())
