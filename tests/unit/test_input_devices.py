# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""G45: o autoconfig gerenciado passa a existir, com todas as recusas no lugar.

Nenhum teste aqui escreve no host: tudo acontece em `tmp_path`. O `retroarch.cfg`
e LIDO em um caso e conferido byte a byte depois — ele e do usuario.
"""

from __future__ import annotations

import os
import stat

import pytest

from steamzero.adapters.input_devices import (
    MANAGED_BASENAME,
    AutoconfigCatalog,
    AutoconfigTarget,
    RetroArchControls,
    SysfsInputDevices,
    resolve_target,
)
from steamzero.domain.retroarch_autoconfig import MANAGED_MARKER, DeviceIdentity, is_managed

_STEAM_CONTROLLER = """
input_driver = "udev"
input_device = "Steam Controller"
input_vendor_id = "10462"
input_product_id = "1142"
input_b_btn = "0"
input_a_btn = "1"
input_y_btn = "2"
input_x_btn = "3"
input_start_btn = "7"
input_select_btn = "6"
input_l_btn = "4"
input_r_btn = "5"
input_up_axis = "-1"
input_down_axis = "+1"
input_left_axis = "-0"
input_right_axis = "+0"
"""

_PERFIL = [
    {"action": "game.up", "input": "hat.up"},
    {"action": "game.down", "input": "hat.down"},
    {"action": "game.left", "input": "hat.left"},
    {"action": "game.right", "input": "hat.right"},
    {"action": "game.primary", "input": "button.south"},
    {"action": "game.secondary", "input": "button.east"},
    {"action": "game.tertiary", "input": "button.west"},
    {"action": "game.quaternary", "input": "button.north"},
    {"action": "game.start", "input": "button.start"},
    {"action": "game.select", "input": "button.select"},
    {"action": "game.shoulder-left", "input": "button.shoulder-left"},
    {"action": "game.shoulder-right", "input": "button.shoulder-right"},
]

_DECK = DeviceIdentity(name="Steam Controller", vendor_id=10462, product_id=1142)


class _Devices:
    def __init__(self, *identities: DeviceIdentity) -> None:
        self._identities = list(identities)

    def identities(self) -> list[DeviceIdentity]:
        return list(self._identities)


def _catalog(tmp_path, **files: str) -> AutoconfigCatalog:
    directory = tmp_path / "bundled"
    directory.mkdir(exist_ok=True)
    for name, text in files.items():
        (directory / f"{name}.cfg").write_text(text, encoding="utf-8")
    return AutoconfigCatalog([directory])


def _controls(tmp_path, devices, *, declared: bool = True, **files: str) -> RetroArchControls:
    target = tmp_path / "autoconfig"
    target.mkdir(exist_ok=True)
    return RetroArchControls(
        devices=devices,
        catalog=_catalog(tmp_path, pad=files.get("pad", _STEAM_CONTROLLER)),
        target=AutoconfigTarget(target, declared=declared),
    )


def _status(controls):
    return controls.status(
        bindings=_PERFIL, profile_id="standard-gamepad", profile_revision=1, orientation="landscape"
    )


def _apply(controls):
    return controls.apply(
        bindings=_PERFIL, profile_id="standard-gamepad", profile_revision=1, orientation="landscape"
    )


class TestReadingTheRealDeviceIdentity:
    def test_sysfs_hex_becomes_the_decimal_the_autoconfig_uses(self, tmp_path) -> None:
        """`28de` no sysfs e `10462` no autoconfig sao o MESMO id.

        Errar a base faria nenhuma busca casar e todo pad ficaria eternamente
        "sem autoconfig" — degradacao silenciosa que parece ausencia de hardware.
        """
        sys_class = tmp_path / "sys"
        device = sys_class / "event5" / "device"
        (device / "id").mkdir(parents=True)
        (device / "name").write_text("Valve Software Steam Deck Controller\n")
        (device / "id" / "vendor").write_text("28de\n")
        (device / "id" / "product").write_text("1205\n")
        by_id = tmp_path / "by-id"
        by_id.mkdir()
        os.symlink(tmp_path / "sys" / "event5", by_id / "usb-Valve-event-joystick")

        found = SysfsInputDevices(by_id=by_id, sys_class=sys_class).identities()

        assert found == [DeviceIdentity("Valve Software Steam Deck Controller", 0x28DE, 0x1205)]
        assert found[0].vendor_id == 10462

    def test_a_host_without_joysticks_reports_none_instead_of_failing(self, tmp_path) -> None:
        assert SysfsInputDevices(by_id=tmp_path / "ausente").identities() == []


class TestMatchingTheDeviceToItsAutoconfig:
    def test_vendor_and_product_select_the_file(self, tmp_path) -> None:
        match = _catalog(tmp_path, pad=_STEAM_CONTROLLER).match([_DECK])

        assert match.reason == "matched"
        assert match.autoconfig is not None

    def test_a_pad_without_a_packaged_autoconfig_stays_unresolved(self, tmp_path) -> None:
        """O proprio controle deste host cai aqui: 10462:4613 nao tem arquivo.

        Sem arquivo nao ha indice, e sem indice a resposta honesta e "nao sei".
        """
        deck_interno = DeviceIdentity("Steam Deck Controller", 10462, 4613)

        match = _catalog(tmp_path, pad=_STEAM_CONTROLLER).match([deck_interno])

        assert match.reason == "no-autoconfig"
        assert match.autoconfig is None

    def test_two_different_pads_are_ambiguous_not_a_coin_flip(self, tmp_path) -> None:
        outro = DeviceIdentity("8Bitdo Pro", 11720, 12289)

        match = _catalog(tmp_path, pad=_STEAM_CONTROLLER).match([_DECK, outro])

        assert match.reason == "ambiguous-device"
        assert match.candidates == ("8Bitdo Pro", "Steam Controller")

    def test_two_files_describing_the_same_pad_differently_are_ambiguous(self, tmp_path) -> None:
        divergente = _STEAM_CONTROLLER.replace('input_b_btn = "0"', 'input_b_btn = "9"')
        catalog = _catalog(tmp_path, pad=_STEAM_CONTROLLER, outro=divergente)

        match = catalog.match([_DECK])

        assert match.reason == "ambiguous-autoconfig"
        assert match.autoconfig is None

    def test_our_own_generated_file_is_never_used_as_a_source(self, tmp_path) -> None:
        """Ler o proprio arquivo gerado realimentaria o resultado como se fosse
        dado do fabricante, e um erro nosso viraria verdade permanente."""
        catalog = _catalog(
            tmp_path,
            pad=_STEAM_CONTROLLER,
            nosso=f"{MANAGED_MARKER}\n{_STEAM_CONTROLLER}",
        )

        assert catalog.match([_DECK]).candidates == ("pad.cfg",)


class TestWhereRetroArchSaysItReadsProfiles:
    def test_the_declared_directory_is_read_from_retroarch_cfg(self, tmp_path) -> None:
        config = tmp_path / "retroarch.cfg"
        config.write_text('joypad_autoconfig_dir = "/casa/perfis"\n', encoding="utf-8")

        target = resolve_target(config)

        assert target.declared is True
        assert target.path is not None and target.path.parent.name == "perfis"

    def test_an_absent_retroarch_cfg_never_claims_a_directory(self, tmp_path) -> None:
        """Este e o caso REAL deste host: o RetroArch nunca gravou configuracao."""
        target = resolve_target(tmp_path / "nao-existe.cfg", tmp_path / "convencional")

        assert target.declared is False

    def test_reading_the_config_does_not_write_to_it(self, tmp_path) -> None:
        """`retroarch.cfg` e do usuario (AGENTS.md §5)."""
        config = tmp_path / "retroarch.cfg"
        original = 'joypad_autoconfig_dir = "/casa/perfis"\nvideo_fullscreen = "true"\n'
        config.write_text(original, encoding="utf-8")
        antes = config.stat().st_mtime_ns

        resolve_target(config)

        assert config.read_text(encoding="utf-8") == original
        assert config.stat().st_mtime_ns == antes


class TestTheStatesTheScreenHasToTellApart:
    def test_no_profile_is_not_configured(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))

        outcome = controls.status(
            bindings=[], profile_id="standard-gamepad", profile_revision=1, orientation="landscape"
        )

        assert outcome.state == "not-configured"

    def test_no_device_is_awaiting_device_not_applied(self, tmp_path) -> None:
        outcome = _status(_controls(tmp_path, _Devices()))

        assert outcome.state == "awaiting-device"
        assert outcome.to_dict()["resolvedBindings"] == []

    def test_an_undeclared_directory_never_reports_applied(self, tmp_path) -> None:
        """Gravar onde ninguem provou que o RetroArch le seria falso verde."""
        outcome = _status(_controls(tmp_path, _Devices(_DECK), declared=False))

        assert outcome.state == "awaiting-emulator"

    def test_everything_resolved_but_not_written_is_pending(self, tmp_path) -> None:
        outcome = _status(_controls(tmp_path, _Devices(_DECK)))

        assert outcome.state == "pending-write"
        assert len(outcome.to_dict()["resolvedBindings"]) == 12

    def test_a_device_missing_some_inputs_is_partial(self, tmp_path) -> None:
        sem_ombros = _STEAM_CONTROLLER.replace('input_l_btn = "4"', "")
        controls = _controls(tmp_path, _Devices(_DECK), pad=sem_ombros)

        outcome = _apply(controls)

        assert outcome.state == "partial"
        payload = outcome.to_dict()
        assert [row["action"] for row in payload["unresolvedBindings"]] == ["game.shoulder-left"]
        assert payload["unresolvedBindings"][0]["reasonLabel"]

    def test_applied_is_only_claimed_after_the_file_exists(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))

        assert _status(controls).state == "pending-write"
        assert _apply(controls).state == "applied"
        assert _status(controls).state == "applied"


class TestTheFileOnDisk:
    def test_the_generated_file_carries_the_ownership_marker(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))

        outcome = _apply(controls)

        assert outcome.target.path is not None
        texto = outcome.target.path.read_text(encoding="utf-8")
        assert texto.splitlines()[0] == MANAGED_MARKER
        assert is_managed(texto)

    def test_every_written_index_came_from_the_device_file(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))

        outcome = _apply(controls)

        assert outcome.target.path is not None
        gravado = outcome.target.path.read_text(encoding="utf-8")
        assert 'input_b_btn = "0"' in gravado
        assert 'input_up_axis = "-1"' in gravado
        assert 'input_left_axis = "-0"' in gravado

    def test_applying_twice_does_not_rewrite_the_file(self, tmp_path) -> None:
        """Idempotencia real: regravar mudaria o mtime sem mudar nada."""
        controls = _controls(tmp_path, _Devices(_DECK))
        primeiro = _apply(controls)
        assert primeiro.target.path is not None
        antes = primeiro.target.path.stat().st_mtime_ns

        segundo = _apply(controls)

        assert segundo.state == "applied"
        assert primeiro.target.path.stat().st_mtime_ns == antes

    def test_the_write_leaves_no_temporary_behind(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))

        outcome = _apply(controls)

        assert outcome.target.directory is not None
        restos = [p.name for p in outcome.target.directory.iterdir() if p.name != MANAGED_BASENAME]
        assert restos == []

    def test_a_changed_profile_updates_the_managed_file_in_place(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))
        _apply(controls)

        girado = controls.apply(
            bindings=[{"action": "game.primary", "input": "button.west"}],
            profile_id="mega-drive-3-button",
            profile_revision=1,
            orientation="landscape",
        )

        assert girado.state == "applied"
        assert girado.target.path is not None
        assert 'input_b_btn = "2"' in girado.target.path.read_text(encoding="utf-8")


class TestWhatIsNotOursIsNotTouched:
    def test_a_file_without_the_marker_is_never_overwritten(self, tmp_path) -> None:
        """AGENTS.md §5: sem marcador, o arquivo e do usuario ou do RetroArch."""
        controls = _controls(tmp_path, _Devices(_DECK))
        alheio = tmp_path / "autoconfig" / MANAGED_BASENAME
        original = 'input_device = "perfil do usuario"\ninput_b_btn = "9"\n'
        alheio.write_text(original, encoding="utf-8")

        outcome = _apply(controls)

        assert outcome.state == "conflict"
        assert alheio.read_text(encoding="utf-8") == original

    def test_a_conflict_is_reported_with_the_path_that_blocked(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))
        (tmp_path / "autoconfig" / MANAGED_BASENAME).write_text('input_b_btn = "9"\n')

        assert MANAGED_BASENAME in _apply(controls).detail

    def test_the_host_directory_keeps_its_own_permissions(self, tmp_path) -> None:
        """Gravar um arquivo nao pode mudar o diretorio do RetroArch.

        `core.fs.write_atomic` faz `chmod 0700` incondicional no pai; usada aqui,
        mudaria a permissao da configuracao alheia (no host, 0750 → 0700) como
        efeito colateral invisivel. AGENTS.md §5 proibe.
        """
        directory = tmp_path / "autoconfig"
        directory.mkdir(exist_ok=True)
        # 0750 e a permissao REAL do diretorio de perfis do RetroArch neste host.
        # O objetivo do teste e justamente provar que ela sobrevive intacta, entao
        # o modo tem de ser reproduzido como esta la.
        os.chmod(directory, 0o750)  # noqa: S103
        controls = RetroArchControls(
            devices=_Devices(_DECK),
            catalog=_catalog(tmp_path, pad=_STEAM_CONTROLLER),
            target=AutoconfigTarget(directory, declared=True),
        )

        assert _apply(controls).state == "applied"
        assert stat.S_IMODE(directory.stat().st_mode) == 0o750

    def test_an_absent_host_directory_is_not_created_by_us(self, tmp_path) -> None:
        """Criar diretorio dentro da configuracao do RetroArch e passar do limite."""
        directory = tmp_path / "nao-existe"
        controls = RetroArchControls(
            devices=_Devices(_DECK),
            catalog=_catalog(tmp_path, pad=_STEAM_CONTROLLER),
            target=AutoconfigTarget(directory, declared=True),
        )

        assert _apply(controls).state == "write-failed"
        assert not directory.exists()

    def test_the_bundled_autoconfig_of_the_vendor_is_never_modified(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))
        empacotado = tmp_path / "bundled" / "pad.cfg"
        antes = empacotado.read_text(encoding="utf-8")

        _apply(controls)

        assert empacotado.read_text(encoding="utf-8") == antes


class TestFailureDegradesAndNeverBlocks:
    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignora permissao de diretorio")
    def test_a_read_only_directory_becomes_write_failed_not_a_crash(self, tmp_path) -> None:
        """Falha degrada para estado visivel; o RetroArch segue usavel (§8)."""
        directory = tmp_path / "autoconfig"
        directory.mkdir()
        controls = RetroArchControls(
            devices=_Devices(_DECK),
            catalog=_catalog(tmp_path, pad=_STEAM_CONTROLLER),
            target=AutoconfigTarget(directory, declared=True),
        )
        os.chmod(directory, stat.S_IRUSR | stat.S_IXUSR)
        try:
            outcome = _apply(controls)
        finally:
            os.chmod(directory, stat.S_IRWXU)

        assert outcome.state == "write-failed"
        assert outcome.detail
        assert outcome.label

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignora permissao de diretorio")
    def test_a_failed_write_leaves_the_previous_managed_file_intact(self, tmp_path) -> None:
        """Atomicidade: nunca existe estado intermediario meio gravado."""
        controls = _controls(tmp_path, _Devices(_DECK))
        primeiro = _apply(controls)
        assert primeiro.target.path is not None
        bom = primeiro.target.path.read_text(encoding="utf-8")

        directory = primeiro.target.directory
        assert directory is not None
        os.chmod(directory, stat.S_IRUSR | stat.S_IXUSR)
        try:
            falho = controls.apply(
                bindings=[{"action": "game.primary", "input": "button.west"}],
                profile_id="mega-drive-3-button",
                profile_revision=1,
                orientation="landscape",
            )
        finally:
            os.chmod(directory, stat.S_IRWXU)

        assert falho.state == "write-failed"
        assert primeiro.target.path.read_text(encoding="utf-8") == bom

    def test_an_unreadable_catalog_directory_does_not_raise(self, tmp_path) -> None:
        match = AutoconfigCatalog([tmp_path / "inexistente"]).match([_DECK])

        assert match.reason == "no-autoconfig"


class TestTheStatusPayload:
    def test_the_payload_carries_everything_the_screen_needs(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))

        payload = _apply(controls).to_dict()

        assert set(payload) == {
            "state",
            "statusLabel",
            "detail",
            "device",
            "deviceReason",
            "autoconfigCandidates",
            "path",
            "directoryDeclared",
            "resolvedBindings",
            "unresolvedBindings",
            "withoutRetropadEquivalent",
        }
        assert payload["state"] == "applied"
        assert payload["device"] == {
            "name": "Steam Controller",
            "vendorId": 10462,
            "productId": 1142,
        }
        assert payload["directoryDeclared"] is True
        assert set(payload["resolvedBindings"][0]) == {"action", "input", "key", "value"}

    def test_an_unresolved_binding_says_why_in_words(self, tmp_path) -> None:
        controls = _controls(
            tmp_path, _Devices(_DECK), pad=_STEAM_CONTROLLER.replace('input_r_btn = "5"', "")
        )

        payload = _apply(controls).to_dict()

        assert payload["unresolvedBindings"] == [
            {
                "action": "game.shoulder-right",
                "input": "button.shoulder-right",
                "reason": "dispositivo-nao-declara",
                "reasonLabel": "O controle conectado não declara essa entrada.",
            }
        ]
