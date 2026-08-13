# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""G45: o autoconfig gerenciado passa a existir, com todas as recusas no lugar.

Nenhum teste aqui escreve no host: tudo acontece em `tmp_path`. O `retroarch.cfg`
e LIDO em um caso e conferido byte a byte depois — ele e do usuario.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from steamzero.adapters.input_devices import (
    _FLATPAK_CONFIG,
    MANAGED_BASENAME,
    AutoconfigCatalog,
    AutoconfigTarget,
    ManagedRetroArchConfig,
    RetroArchControls,
    SysfsInputDevices,
    managed_config,
    resolve_target,
)
from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError
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


def _managed_at(tmp_path) -> ManagedRetroArchConfig:
    """Arvore gerenciada do SteamZero — o unico alvo de escrita em producao."""
    return ManagedRetroArchConfig(root=tmp_path / "steamzero-retroarch", driver="udev")


def _controls(tmp_path, devices, *, declared: bool = True, **files: str) -> RetroArchControls:
    managed = _managed_at(tmp_path)
    return RetroArchControls(
        devices=devices,
        catalog=_catalog(tmp_path, pad=files.get("pad", _STEAM_CONTROLLER)),
        target=managed.target if declared else AutoconfigTarget(None, declared=False),
        managed=managed if declared else None,
    )


def _status_of(controls):
    return _status(controls)


def _status(controls):
    return controls.status(
        bindings=_PERFIL, profile_id="standard-gamepad", profile_revision=1, orientation="landscape"
    )


def _apply(controls, bindings=None):
    """Planeja e aplica pelo núcleo transacional, devolvendo o estado observado.

    Não existe mais escrita fora da transação: o conteúdo vai DENTRO do plano, a
    precondição guarda o fingerprint do destino e o commit só acontece depois de
    o arquivo estar gravado e verificado. Quando `plan()` recusa, o estado
    observado já explica a recusa.
    """
    argumentos = {
        "bindings": bindings if bindings is not None else _PERFIL,
        "profile_id": "standard-gamepad",
        "profile_revision": 1,
        "orientation": "landscape",
    }
    try:
        plan = controls.plan(**argumentos)
    except SteamZeroError:
        return controls.status(**argumentos)
    controls.apply(plan.plan_id, plan.confirm_token)
    return controls.status(**argumentos)


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
        # `perfis/udev`, nao `perfis`: o driver entra no caminho (ver o teste do
        # subdiretorio abaixo, medido no pacote real).
        assert target.path is not None
        assert target.path.parent == Path("/casa/perfis/udev")

    def test_the_driver_subdirectory_is_part_of_the_target(self, tmp_path) -> None:
        """O RetroArch procura em `<dir>/<driver>/`, nao na raiz.

        Medido no pacote 1.22.2 instalado: a raiz de `share/libretro/autoconfig`
        tem ZERO `.cfg`, e `udev/` tem 420. Gravar na raiz produziria um arquivo
        que nunca seria lido — falha silenciosa.
        """
        config = tmp_path / "retroarch.cfg"
        config.write_text(
            'joypad_autoconfig_dir = "/casa/perfis"\ninput_joypad_driver = "udev"\n',
            encoding="utf-8",
        )

        target = resolve_target(config)

        assert target.directory == Path("/casa/perfis/udev")

    def test_the_driver_comes_from_the_config_not_from_a_guess(self, tmp_path) -> None:
        config = tmp_path / "retroarch.cfg"
        config.write_text(
            'joypad_autoconfig_dir = "/casa/perfis"\ninput_joypad_driver = "sdl2"\n',
            encoding="utf-8",
        )

        assert resolve_target(config).directory == Path("/casa/perfis/sdl2")

    def test_the_sandbox_path_the_flatpak_really_declares_is_not_reachable(self, tmp_path) -> None:
        """Valor LITERAL do config que o RetroArch Flatpak cria neste host.

        `/app` e o mount somente-leitura do sandbox e nao existe fora dele.
        Diretorio DECLARADO nao implica diretorio ALCANCAVEL, e abrir o
        RetroArch nao resolve isso.
        """
        config = tmp_path / "retroarch.cfg"
        config.write_text(
            'joypad_autoconfig_dir = "/app/share/libretro/autoconfig"\n'
            'input_joypad_driver = "udev"\n',
            encoding="utf-8",
        )
        target = resolve_target(config)
        assert target.declared is True
        assert target.directory == Path("/app/share/libretro/autoconfig/udev")

        controls = RetroArchControls(
            devices=_Devices(_DECK),
            catalog=_catalog(tmp_path, pad=_STEAM_CONTROLLER),
            target=target,
        )
        outcome = _apply(controls)

        assert outcome.state == "awaiting-emulator"
        assert "sandbox" in outcome.detail
        assert not Path("/app").exists()

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

    def test_a_partial_profile_is_diagnosed_and_NOT_written(self, tmp_path) -> None:
        """Meio perfil em disco é pior que perfil nenhum.

        O RetroArch aceitaria o arquivo, as ações faltantes ficariam sem binding
        e o controle responderia pela metade sem nada dizer por quê. O critério
        desta entrega é gravar somente com tudo resolvido, então `partial` é
        diagnóstico: aparece na tela com o motivo e o emulador segue nos padrões
        dele.
        """
        sem_ombros = _STEAM_CONTROLLER.replace('input_l_btn = "4"', "")
        controls = _controls(tmp_path, _Devices(_DECK), pad=sem_ombros)

        outcome = _apply(controls)

        assert outcome.state == "partial"
        payload = outcome.to_dict()
        assert [row["action"] for row in payload["unresolvedBindings"]] == ["game.shoulder-left"]
        assert payload["unresolvedBindings"][0]["reasonLabel"]
        assert outcome.target.path is not None
        assert not outcome.target.path.exists()

    def test_a_profile_that_became_partial_does_not_erase_what_was_applied(self, tmp_path) -> None:
        """Recusar gravar não é remover: o perfil anterior continua valendo.

        Troca do pad completo por um que não declara os ombros — a resolução
        vira parcial e a gravação é recusada, mas o arquivo que já estava
        aplicado permanece intacto.
        """
        alvo = tmp_path / "autoconfig"
        alvo.mkdir()
        completo = _catalog(tmp_path, pad=_STEAM_CONTROLLER)
        controls = RetroArchControls(
            devices=_Devices(_DECK),
            catalog=completo,
            target=AutoconfigTarget(alvo, declared=True),
        )
        aplicado = _apply(controls)
        assert aplicado.state == "applied"
        bom = (alvo / MANAGED_BASENAME).read_text(encoding="utf-8")

        degradado = tmp_path / "degradado"
        degradado.mkdir()
        (degradado / "pad.cfg").write_text(
            _STEAM_CONTROLLER.replace('input_l_btn = "4"', ""), encoding="utf-8"
        )
        parcial = _apply(
            RetroArchControls(
                devices=_Devices(_DECK),
                catalog=AutoconfigCatalog([degradado]),
                target=AutoconfigTarget(alvo, declared=True),
            )
        )

        assert parcial.state == "partial"
        assert (alvo / MANAGED_BASENAME).read_text(encoding="utf-8") == bom

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

        girado = _apply(controls, bindings=[{"action": "game.primary", "input": "button.west"}])

        assert girado.state == "applied"
        assert girado.target.path is not None
        assert 'input_b_btn = "2"' in girado.target.path.read_text(encoding="utf-8")


class TestTheWindowInsideTheTransaction:
    def test_an_intruder_created_after_staging_is_not_overwritten(
        self, tmp_path, monkeypatch
    ) -> None:
        """A janela que a revalidação de preconditions NÃO cobria.

        `_revalidate_preconditions` roda UMA vez, no início do apply, e depois
        ainda acontecem staging e backup. Um arquivo estrangeiro criado nesse
        intervalo era copiado para o backup e então sobrescrito pela escrita,
        com a operação retornando `ok`: a garantia de nunca destruir arquivo
        alheio valia só até o staging.

        O teste anterior inseria o intruso ANTES de `apply()` e por isso passava
        sem tocar nessa janela. Aqui ele é criado exatamente dentro dela.
        """
        controls = _controls(tmp_path, _Devices(_DECK))
        argumentos = {
            "bindings": _PERFIL,
            "profile_id": "standard-gamepad",
            "profile_revision": 1,
            "orientation": "landscape",
        }
        plan = controls.plan(**argumentos)
        alvo = tmp_path / "steamzero-retroarch" / "autoconfig" / "udev" / MANAGED_BASENAME
        alvo.parent.mkdir(parents=True, exist_ok=True)
        intruso = 'input_device = "criado dentro da janela"\n'

        original = transaction._stage

        def stage_e_intruso(*args: object, **kwargs: object) -> object:
            resultado = original(*args, **kwargs)  # type: ignore[arg-type]
            alvo.write_text(intruso, encoding="utf-8")
            return resultado

        monkeypatch.setattr(transaction, "_stage", stage_e_intruso)

        with pytest.raises(SteamZeroError) as erro:
            controls.apply(plan.plan_id, plan.confirm_token)

        assert erro.value.code == "E-TX-STALE-PLAN"
        assert alvo.read_text(encoding="utf-8") == intruso

    def test_an_update_whose_target_changed_inside_the_window_is_refused(
        self, tmp_path, monkeypatch
    ) -> None:
        """Mesma janela, agora com alvo que EXISTIA e mudou no meio."""
        controls = _controls(tmp_path, _Devices(_DECK))
        _apply(controls)
        alvo = tmp_path / "steamzero-retroarch" / "autoconfig" / "udev" / MANAGED_BASENAME
        alvo.parent.mkdir(parents=True, exist_ok=True)

        plan = controls.plan(
            bindings=[{"action": "game.primary", "input": "button.west"}],
            profile_id="mega-drive-3-button",
            profile_revision=1,
            orientation="landscape",
        )
        alterado = f'{MANAGED_MARKER}\ninput_b_btn = "9"\n'

        original = transaction._stage

        def stage_e_alteracao(*args: object, **kwargs: object) -> object:
            resultado = original(*args, **kwargs)  # type: ignore[arg-type]
            alvo.write_text(alterado, encoding="utf-8")
            return resultado

        monkeypatch.setattr(transaction, "_stage", stage_e_alteracao)

        with pytest.raises(SteamZeroError) as erro:
            controls.apply(plan.plan_id, plan.confirm_token)

        assert erro.value.code == "E-TX-STALE-PLAN"
        assert alvo.read_text(encoding="utf-8") == alterado


class TestTheAppendconfigIntegration:
    """O mecanismo que faz o perfil chegar ao RetroArch sem editar o config dele.

    O RetroArch Flatpak procura perfis em `/app/share/libretro/autoconfig`, que
    e interno ao sandbox e inalcancavel do host. `--appendconfig` sobrepoe a
    chave apontando para uma arvore NOSSA.
    """

    def _managed(self, tmp_path, driver: str = "udev") -> ManagedRetroArchConfig:
        return ManagedRetroArchConfig(root=tmp_path / "steamzero-retroarch", driver=driver)

    def _controls_managed(self, tmp_path, managed) -> RetroArchControls:
        return RetroArchControls(
            devices=_Devices(_DECK),
            catalog=_catalog(tmp_path, pad=_STEAM_CONTROLLER),
            target=managed.target,
            managed=managed,
        )

    def test_the_overlay_redirects_the_directory_retroarch_reads(self, tmp_path) -> None:
        managed = self._managed(tmp_path)
        conteudo = managed.overlay_content()

        assert f'joypad_autoconfig_dir = "{managed.autoconfig_root}"' in conteudo
        assert conteudo.splitlines()[0] == MANAGED_MARKER

    def test_the_overlay_disables_save_on_exit(self, tmp_path) -> None:
        """Sem isto, o RetroArch gravaria nossa injecao no config do USUARIO.

        `config_save_on_exit` vem `true` de fabrica; ao sair, o RetroArch
        reescreve o arquivo em uso com os valores efetivos — inclusive os que
        vieram do `--appendconfig`. Isso equivaleria a editar permanentemente a
        configuracao dele, que a AGENTS.md §5 proibe.
        """
        assert 'config_save_on_exit = "false"' in self._managed(tmp_path).overlay_content()

    def test_the_profile_goes_under_the_driver_the_user_config_declares(self, tmp_path) -> None:
        assert self._managed(tmp_path, "sdl2").target.directory == (
            tmp_path / "steamzero-retroarch" / "autoconfig" / "sdl2"
        )

    def test_the_driver_is_read_from_the_user_config(self, tmp_path) -> None:
        config = tmp_path / _FLATPAK_CONFIG
        config.mkdir(parents=True)
        (config / "retroarch.cfg").write_text('input_joypad_driver = "dinput"\n', encoding="utf-8")

        assert managed_config(tmp_path).driver == "dinput"

    def test_a_host_without_retroarch_config_falls_back_to_udev(self, tmp_path) -> None:
        assert managed_config(tmp_path).driver == "udev"

    def test_applying_writes_the_profile_AND_the_overlay(self, tmp_path) -> None:
        """Um sem o outro nao vale: perfil sem overlay nunca e procurado, e
        overlay sem perfil aponta para diretorio vazio."""
        managed = self._managed(tmp_path)
        controls = self._controls_managed(tmp_path, managed)

        outcome = _apply(controls)

        assert outcome.state == "applied"
        assert managed.overlay_path.is_file()
        assert (managed.autoconfig_root / "udev" / MANAGED_BASENAME).is_file()

    def test_a_profile_without_the_overlay_is_not_applied(self, tmp_path) -> None:
        managed = self._managed(tmp_path)
        controls = self._controls_managed(tmp_path, managed)
        _apply(controls)
        managed.overlay_path.unlink()

        assert _status_of(controls).state == "pending-write"

    def test_a_foreign_overlay_is_never_overwritten(self, tmp_path) -> None:
        managed = self._managed(tmp_path)
        controls = self._controls_managed(tmp_path, managed)
        _apply(controls)
        alheio = 'joypad_autoconfig_dir = "/do/usuario"\n'
        managed.overlay_path.write_text(alheio, encoding="utf-8")

        outcome = _status_of(controls)

        assert outcome.state == "conflict"
        assert managed.overlay_path.read_text(encoding="utf-8") == alheio

    def test_rolling_back_removes_the_overlay_too(self, tmp_path) -> None:
        managed = self._managed(tmp_path)
        controls = self._controls_managed(tmp_path, managed)
        argumentos = {
            "bindings": _PERFIL,
            "profile_id": "standard-gamepad",
            "profile_revision": 1,
            "orientation": "landscape",
        }
        plan = controls.plan(**argumentos)
        resultado = controls.apply(plan.plan_id, plan.confirm_token)
        assert managed.overlay_path.is_file()

        transaction.rollback(resultado.operation_id, reason="teste")

        assert not managed.overlay_path.exists()

    def test_the_launch_arguments_are_the_ones_retroarch_accepts(self, tmp_path) -> None:
        managed = self._managed(tmp_path)

        assert managed.launch_arguments() == ("--appendconfig", str(managed.overlay_path))


class TestRollbackIsRealNotDeclared:
    def test_rolling_back_removes_the_file_it_created(self, tmp_path) -> None:
        """`G-FULL` precisa ser verdade, não rótulo.

        Antes, o efeito acontecia FORA da transação e o plano não tinha ações.
        O histórico oferecia rollback e classificava tudo como `G-FULL`, mas
        desfazer marcava a operação como revertida e deixava o autoconfig no
        disco — rollback falso. Com o conteúdo dentro do plano, desfazer remove
        de fato o arquivo que a operação criou.
        """
        controls = _controls(tmp_path, _Devices(_DECK))
        argumentos = {
            "bindings": _PERFIL,
            "profile_id": "standard-gamepad",
            "profile_revision": 1,
            "orientation": "landscape",
        }
        plan = controls.plan(**argumentos)
        resultado = controls.apply(plan.plan_id, plan.confirm_token)
        alvo = tmp_path / "steamzero-retroarch" / "autoconfig" / "udev" / MANAGED_BASENAME
        alvo.parent.mkdir(parents=True, exist_ok=True)
        assert alvo.is_file()

        transaction.rollback(resultado.operation_id, reason="teste")

        assert not alvo.exists()
        assert controls.status(**argumentos).state == "pending-write"

    def test_rolling_back_an_update_restores_the_previous_content(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))
        _apply(controls)
        alvo = tmp_path / "steamzero-retroarch" / "autoconfig" / "udev" / MANAGED_BASENAME
        alvo.parent.mkdir(parents=True, exist_ok=True)
        anterior = alvo.read_text(encoding="utf-8")

        plan = controls.plan(
            bindings=[{"action": "game.primary", "input": "button.west"}],
            profile_id="mega-drive-3-button",
            profile_revision=1,
            orientation="landscape",
        )
        resultado = controls.apply(plan.plan_id, plan.confirm_token)
        assert alvo.read_text(encoding="utf-8") != anterior

        transaction.rollback(resultado.operation_id, reason="teste")

        assert alvo.read_text(encoding="utf-8") == anterior


class TestWhatIsNotOursIsNotTouched:
    def test_a_file_without_the_marker_is_never_overwritten(self, tmp_path) -> None:
        """AGENTS.md §5: sem marcador, o arquivo e do usuario ou do RetroArch."""
        controls = _controls(tmp_path, _Devices(_DECK))
        alheio = tmp_path / "steamzero-retroarch" / "autoconfig" / "udev" / MANAGED_BASENAME
        alheio.parent.mkdir(parents=True, exist_ok=True)
        original = 'input_device = "perfil do usuario"\ninput_b_btn = "9"\n'
        alheio.write_text(original, encoding="utf-8")

        outcome = _apply(controls)

        assert outcome.state == "conflict"
        assert alheio.read_text(encoding="utf-8") == original

    @pytest.mark.parametrize(
        ("nome", "motivo"),
        [
            ("symlink", "link simbólico"),
            ("oversized", "grande demais"),
            ("unreadable", "não pôde ser lido"),
            ("not-regular", "não é um arquivo regular"),
        ],
    )
    def test_an_unverifiable_target_is_foreign_not_absent(self, tmp_path, nome, motivo) -> None:
        """Só a AUSÊNCIA comprovada autoriza gravar.

        A leitura tolerante devolvia `None` tanto para arquivo inexistente
        quanto para symlink, arquivo grande demais e arquivo ilegível — e quem
        lia esse `None` concluía "ausente, pode escrever". Um `steamzero.cfg` do
        usuário em qualquer dessas formas seria substituído sem que o marcador
        fosse conferido uma única vez.
        """
        controls = _controls(tmp_path, _Devices(_DECK))
        alvo = tmp_path / "steamzero-retroarch" / "autoconfig" / "udev" / MANAGED_BASENAME
        alvo.parent.mkdir(parents=True, exist_ok=True)
        if nome == "symlink":
            outro = tmp_path / "arquivo-do-usuario.cfg"
            outro.write_text('input_b_btn = "9"\n', encoding="utf-8")
            os.symlink(outro, alvo)
        elif nome == "oversized":
            alvo.write_text("#" * (128 * 1024 + 1), encoding="utf-8")
        elif nome == "unreadable":
            alvo.write_text('input_b_btn = "9"\n', encoding="utf-8")
            os.chmod(alvo, 0)
        else:
            alvo.mkdir()

        try:
            outcome = _apply(controls)
        finally:
            if nome == "unreadable":
                os.chmod(alvo, stat.S_IRUSR | stat.S_IWUSR)

        assert outcome.state == "conflict"
        assert motivo in outcome.detail
        # E o alvo continua sendo o que era.
        if nome == "symlink":
            assert alvo.is_symlink()
        elif nome == "not-regular":
            assert alvo.is_dir()

    @pytest.mark.skipif(os.geteuid() == 0, reason="root lê arquivo sem permissão")
    def test_an_unreadable_target_is_never_replaced(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))
        alvo = tmp_path / "steamzero-retroarch" / "autoconfig" / "udev" / MANAGED_BASENAME
        alvo.parent.mkdir(parents=True, exist_ok=True)
        original = 'input_device = "perfil do usuario"\n'
        alvo.write_text(original, encoding="utf-8")
        os.chmod(alvo, 0)
        try:
            outcome = _apply(controls)
        finally:
            os.chmod(alvo, stat.S_IRUSR | stat.S_IWUSR)

        assert outcome.state == "conflict"
        assert alvo.read_text(encoding="utf-8") == original

    def test_a_foreign_file_appearing_between_plan_and_apply_is_not_overwritten(
        self, tmp_path
    ) -> None:
        """A CORRIDA integrada, não só a primitiva.

        A versão anterior verificava o alvo e só então escolhia entre escrita
        exclusiva e `os.replace`. A verificação era refeita imediatamente antes
        de gravar, e um arquivo estrangeiro que aparecesse na janela fazia a
        checagem dizer "estrangeiro" — o que DESLIGAVA a criação exclusiva e
        levava ao `os.replace`, sobrescrevendo exatamente o arquivo que deveria
        proteger. A garantia estava invertida.

        Agora o conteúdo vai dentro do plano e a precondição guarda o
        fingerprint do destino. Um arquivo que apareça entre planejar e aplicar
        muda o fingerprint, e `apply` reprova como plano obsoleto.
        """
        controls = _controls(tmp_path, _Devices(_DECK))
        argumentos = {
            "bindings": _PERFIL,
            "profile_id": "standard-gamepad",
            "profile_revision": 1,
            "orientation": "landscape",
        }
        plan = controls.plan(**argumentos)

        alvo = tmp_path / "steamzero-retroarch" / "autoconfig" / "udev" / MANAGED_BASENAME
        alvo.parent.mkdir(parents=True, exist_ok=True)
        intruso = 'input_device = "chegou entre o plano e o apply"\n'
        alvo.write_text(intruso, encoding="utf-8")

        with pytest.raises(SteamZeroError) as erro:
            controls.apply(plan.plan_id, plan.confirm_token)

        assert erro.value.code == "E-TX-STALE-PLAN"
        assert alvo.read_text(encoding="utf-8") == intruso

    def test_a_profile_changed_after_confirmation_does_not_write_the_other_one(
        self, tmp_path
    ) -> None:
        """Confirmar o perfil A e gravar o B seria trocar a decisão do usuário.

        O plano carrega o CONTEÚDO, então ele está amarrado ao perfil exato que
        foi confirmado; não há como o apply produzir outro.
        """
        controls = _controls(tmp_path, _Devices(_DECK))
        plan = controls.plan(
            bindings=[{"action": "game.primary", "input": "button.west"}],
            profile_id="mega-drive-3-button",
            profile_revision=1,
            orientation="landscape",
        )

        controls.apply(plan.plan_id, plan.confirm_token)

        gravado = (
            tmp_path / "steamzero-retroarch" / "autoconfig" / "udev" / MANAGED_BASENAME
        ).read_text(encoding="utf-8")
        assert 'input_b_btn = "2"' in gravado
        assert "mega-drive-3-button" in gravado

    def test_the_plan_is_single_use(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))
        argumentos = {
            "bindings": _PERFIL,
            "profile_id": "standard-gamepad",
            "profile_revision": 1,
            "orientation": "landscape",
        }
        plan = controls.plan(**argumentos)
        controls.apply(plan.plan_id, plan.confirm_token)

        with pytest.raises(SteamZeroError):
            controls.apply(plan.plan_id, plan.confirm_token)

    def test_a_wrong_token_never_writes(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))
        plan = controls.plan(
            bindings=_PERFIL,
            profile_id="standard-gamepad",
            profile_revision=1,
            orientation="landscape",
        )

        with pytest.raises(SteamZeroError) as erro:
            controls.apply(plan.plan_id, "token-errado")

        assert erro.value.code == "E-TX-CONFIRM-REQUIRED"
        assert not (
            tmp_path / "steamzero-retroarch" / "autoconfig" / "udev" / MANAGED_BASENAME
        ).exists()

    def test_a_conflict_is_reported_with_the_path_that_blocked(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))
        (tmp_path / "steamzero-retroarch" / "autoconfig" / "udev" / MANAGED_BASENAME).parent.mkdir(
            parents=True, exist_ok=True
        )
        (tmp_path / "steamzero-retroarch" / "autoconfig" / "udev" / MANAGED_BASENAME).write_text(
            'input_b_btn = "9"\n'
        )

        assert MANAGED_BASENAME in _apply(controls).detail

    def test_the_managed_tree_is_created_with_our_own_secure_mode(self, tmp_path) -> None:
        """A arvore de perfis e do SteamZero, entao cria-la e legitimo.

        A versao anterior gravava dentro da configuracao do RetroArch e por isso
        precisava poupar o diretorio alheio do `chmod`. Com o `--appendconfig`
        apontando o emulador para uma arvore NOSSA, esse cuidado deixou de ser
        necessario — e a mudanca ampla que ele exigia no nucleo transacional foi
        revertida.
        """
        controls = _controls(tmp_path, _Devices(_DECK))

        assert _apply(controls).state == "applied"

        arvore = tmp_path / "steamzero-retroarch" / "autoconfig" / "udev"
        assert stat.S_IMODE(arvore.stat().st_mode) == 0o700

    def test_an_absent_host_directory_is_not_created_by_us(self, tmp_path) -> None:
        """Criar diretorio dentro da configuracao do RetroArch e passar do limite.

        Se o RetroArch declarou uma pasta que ainda nao existe, ele ainda nao
        montou a arvore de configuracao dele; o estado honesto e esperar, nao
        construir na casa dos outros.
        """
        directory = tmp_path / "nao-existe"
        controls = RetroArchControls(
            devices=_Devices(_DECK),
            catalog=_catalog(tmp_path, pad=_STEAM_CONTROLLER),
            target=AutoconfigTarget(directory, declared=True),
        )

        assert _apply(controls).state == "awaiting-emulator"
        assert not directory.exists()

    def test_the_bundled_autoconfig_of_the_vendor_is_never_modified(self, tmp_path) -> None:
        controls = _controls(tmp_path, _Devices(_DECK))
        empacotado = tmp_path / "bundled" / "pad.cfg"
        antes = empacotado.read_text(encoding="utf-8")

        _apply(controls)

        assert empacotado.read_text(encoding="utf-8") == antes


class TestFailureDegradesAndNeverBlocks:
    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignora permissao de diretorio")
    def test_a_read_only_root_fails_the_operation_instead_of_committing(self, tmp_path) -> None:
        """Falha de escrita reprova a OPERACAO, nao devolve sucesso.

        Antes, o efeito acontecia depois do commit e seu resultado era
        descartado: uma escrita impossivel ainda devolvia sucesso transacional.
        Agora o efeito E a transacao.
        """
        controls = _controls(tmp_path, _Devices(_DECK))
        argumentos = {
            "bindings": _PERFIL,
            "profile_id": "standard-gamepad",
            "profile_revision": 1,
            "orientation": "landscape",
        }
        plan = controls.plan(**argumentos)
        raiz = tmp_path / "steamzero-retroarch"
        raiz.mkdir(parents=True, exist_ok=True)
        os.chmod(raiz, stat.S_IRUSR | stat.S_IXUSR)
        try:
            with pytest.raises(PermissionError):
                controls.apply(plan.plan_id, plan.confirm_token)
        finally:
            os.chmod(raiz, stat.S_IRWXU)

        assert controls.status(**argumentos).state == "pending-write"
        assert not (raiz / "autoconfig" / "udev" / MANAGED_BASENAME).exists()

    def test_a_failed_write_leaves_the_previous_managed_file_intact(
        self, tmp_path, monkeypatch
    ) -> None:
        """Atomicidade: nunca existe estado intermediario meio gravado.

        A falha e injetada na propria escrita, que e o que a garantia cobre: o
        nucleo fez backup antes de tocar no alvo e reverte ao falhar.
        """
        controls = _controls(tmp_path, _Devices(_DECK))
        primeiro = _apply(controls)
        assert primeiro.target.path is not None
        bom = primeiro.target.path.read_text(encoding="utf-8")

        plan = controls.plan(
            bindings=[{"action": "game.primary", "input": "button.west"}],
            profile_id="mega-drive-3-button",
            profile_revision=1,
            orientation="landscape",
        )

        from steamzero.core import fs

        original = fs.write_atomic

        def falha_no_perfil(path, data, **kwargs):  # type: ignore[no-untyped-def]
            if path.name == MANAGED_BASENAME and path.parent.name == "udev":
                raise PermissionError("falha injetada na publicacao do perfil")
            return original(path, data, **kwargs)

        monkeypatch.setattr(fs, "write_atomic", falha_no_perfil)

        with pytest.raises(PermissionError):
            controls.apply(plan.plan_id, plan.confirm_token)

        monkeypatch.undo()
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
