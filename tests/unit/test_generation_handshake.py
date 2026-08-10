# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Handshake de geração entre cliente e daemon.

A regressão da a37 não emitiu erro nenhum: ``current`` apontava para a a37 e o
``steamzero-core.service`` seguia executando o Python da a35, então a UI recebia
snapshots antigos e o sintoma apareceu como "ícones sumiram" e "keys apagadas".
O daemon já publicava ``system.hello`` com a versão — mas ninguém chamava.

Nenhum teste aqui abre socket real nem toca o host.
"""

from __future__ import annotations

from typing import Any

import pytest

from steamzero.service import client as core_client
from steamzero.service.client import CoreGenerationMismatch

_A37 = "2aaa01d9d8b638b3d8e8c396ffbeed133da50ec2"
_A35 = "7a1916e1e711bbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _identity(version: str, commit: str) -> dict[str, str]:
    return {
        "packageVersion": version,
        "sourceCommit": commit,
        "releaseId": f"{version}-{commit[:12]}",
        "sourceDirty": False,  # type: ignore[dict-item]
    }


@pytest.fixture
def daemon_says(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def _install(result: dict[str, Any]) -> None:
        monkeypatch.setattr(core_client, "_call", lambda _id, _m, _p, timeout=2.0: result)

    return _install


@pytest.fixture
def local_is(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from steamzero.core.identity import RuntimeIdentity

    def _install(version: str, commit: str) -> None:
        identity = RuntimeIdentity(
            package_version=version,
            source_commit=commit,
            source_dirty=False,
            release_id=f"{version}-{commit[:12]}" if commit != "unknown" else "",
        )
        monkeypatch.setattr("steamzero.core.identity.runtime_identity", lambda: identity)

    return _install


class TestDaemonIdentity:
    def test_reads_published_identity(self, daemon_says) -> None:  # type: ignore[no-untyped-def]
        daemon_says({"identity": _identity("0.1.0a37", _A37), "daemonVersion": "0.1.0a37"})
        assert core_client.daemon_identity()["sourceCommit"] == _A37

    def test_falls_back_to_version_on_older_daemon(self, daemon_says) -> None:  # type: ignore[no-untyped-def]
        """Daemon anterior à publicação de identidade declara o que sabe."""
        daemon_says({"daemonVersion": "0.1.0a35"})
        identity = core_client.daemon_identity()
        assert identity["packageVersion"] == "0.1.0a35"
        assert identity["sourceCommit"] == ""


class TestVerifyGeneration:
    def test_same_generation_passes(self, daemon_says, local_is) -> None:  # type: ignore[no-untyped-def]
        local_is("0.1.0a37", _A37)
        daemon_says({"identity": _identity("0.1.0a37", _A37)})
        assert core_client.verify_generation()["sourceCommit"] == _A37

    def test_a37_scenario_is_refused(self, daemon_says, local_is) -> None:  # type: ignore[no-untyped-def]
        """Cliente a37 falando com daemon a35: o incidente literal."""
        local_is("0.1.0a37", _A37)
        daemon_says({"identity": _identity("0.1.0a35", _A35)})
        with pytest.raises(CoreGenerationMismatch) as excinfo:
            core_client.verify_generation()
        assert "0.1.0a37" in str(excinfo.value)
        assert "0.1.0a35" in str(excinfo.value)

    def test_same_version_different_commit_is_refused(self, daemon_says, local_is) -> None:  # type: ignore[no-untyped-def]
        """Duas builds da mesma versão a partir de commits diferentes."""
        local_is("0.1.0a37", _A37)
        daemon_says({"identity": _identity("0.1.0a37", _A35)})
        with pytest.raises(CoreGenerationMismatch):
            core_client.verify_generation()

    def test_older_daemon_without_identity_is_refused(self, daemon_says, local_is) -> None:  # type: ignore[no-untyped-def]
        """Sem identidade não há prova de compatibilidade: recusar."""
        local_is("0.1.0a37", _A37)
        daemon_says({"daemonVersion": "0.1.0a37"})
        with pytest.raises(CoreGenerationMismatch):
            core_client.verify_generation()

    def test_unknown_local_identity_is_refused(self, daemon_says, local_is) -> None:  # type: ignore[no-untyped-def]
        """Pacote sem proveniência não pode validar geração alheia."""
        local_is("0.1.0a37", "unknown")
        daemon_says({"identity": _identity("0.1.0a37", _A37)})
        with pytest.raises(CoreGenerationMismatch):
            core_client.verify_generation()

    def test_mismatch_carries_both_sides(self, daemon_says, local_is) -> None:  # type: ignore[no-untyped-def]
        """O erro precisa dizer QUEM diverge, não apenas que divergiu."""
        local_is("0.1.0a37", _A37)
        daemon_says({"identity": _identity("0.1.0a35", _A35)})
        with pytest.raises(CoreGenerationMismatch) as excinfo:
            core_client.verify_generation()
        assert excinfo.value.client["sourceCommit"] == _A37
        assert excinfo.value.daemon["sourceCommit"] == _A35


class TestDaemonPublishesIdentity:
    def test_hello_includes_identity(self) -> None:
        import json

        from steamzero.core.identity import runtime_identity
        from steamzero.service.core import _dispatch

        raw = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "system.hello"}).encode()
        response, _ = _dispatch(raw)
        identity = response["result"]["identity"]
        assert identity["packageVersion"] == runtime_identity().package_version
        for field in ("packageVersion", "sourceCommit", "releaseId"):
            assert field in identity


class TestProvenanceAsymmetry:
    """Um lado com proveniência e outro sem é a assimetria da a37."""

    def test_known_client_refuses_unknown_daemon(self, daemon_says, local_is) -> None:  # type: ignore[no-untyped-def]
        """Release nova conhece sua origem; o processo sobrevivente não."""
        local_is("0.1.0a37", _A37)
        daemon_says({"identity": {"packageVersion": "0.1.0a37", "sourceCommit": "unknown"}})
        with pytest.raises(CoreGenerationMismatch):
            core_client.verify_generation()

    def test_unknown_client_refuses_known_daemon(self, daemon_says, local_is) -> None:  # type: ignore[no-untyped-def]
        local_is("0.1.0a37", "unknown")
        daemon_says({"identity": _identity("0.1.0a37", _A37)})
        with pytest.raises(CoreGenerationMismatch):
            core_client.verify_generation()


class TestDevelopmentTree:
    """Sem proveniência dos dois lados não há release a proteger.

    Exigir proveniência é papel do preflight de promoção, que reprova identidade
    ausente ANTES de instalar. Recusar aqui tornaria o daemon inutilizável em
    desenvolvimento sem ganho de segurança.
    """

    def test_both_unknown_same_version_is_accepted(self, daemon_says, local_is) -> None:  # type: ignore[no-untyped-def]
        local_is("0.1.0a37", "unknown")
        daemon_says({"identity": {"packageVersion": "0.1.0a37", "sourceCommit": "unknown"}})
        assert core_client.verify_generation() is not None

    def test_both_unknown_different_version_is_refused(self, daemon_says, local_is) -> None:  # type: ignore[no-untyped-def]
        """Versões diferentes já são prova de divergência, sem precisar do commit."""
        local_is("0.1.0a37", "unknown")
        daemon_says({"identity": {"packageVersion": "0.1.0a35", "sourceCommit": "unknown"}})
        with pytest.raises(CoreGenerationMismatch):
            core_client.verify_generation()


class TestCliRefusesMutationOnMismatch:
    """Contrato: leitura pode degradar; mutação nunca vai ao daemon errado.

    E também não é repetida localmente — repetir é como se produz efeito
    duplicado quando o resultado da primeira tentativa é ambíguo.
    """

    def _arrange(self, monkeypatch: pytest.MonkeyPatch, *, mutation: bool) -> tuple[str, str]:
        from types import SimpleNamespace

        from steamzero.service import client as mod
        from steamzero.service.methods import CLI_METHODS

        def _boom(**_kw: Any) -> None:
            raise CoreGenerationMismatch(_identity("0.1.0a37", _A37), _identity("0.1.0a35", _A35))

        monkeypatch.setattr(mod, "verify_generation", _boom)
        monkeypatch.delenv("STEAMZERO_NO_DAEMON", raising=False)
        key = ("fake", "acao")
        monkeypatch.setitem(
            CLI_METHODS,
            key,
            SimpleNamespace(
                method="fake.acao",
                mutation=mutation,
                args_to_params=lambda _a, _c: {},
            ),
        )
        return key

    def test_mutation_is_refused_with_structured_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from steamzero.cli import main as cli

        domain, action = self._arrange(monkeypatch, mutation=True)
        result = cli._try_daemon(domain, action, [], "corr-1")

        assert result is not None, "mutação não pode cair no caminho local"
        envelope, code = result
        assert code == cli.EXIT_FAILURE
        assert envelope["error"]["code"] == "E-API-GENERATION-MISMATCH"
        assert "0.1.0a35" in envelope["error"]["detail"]

    def test_read_falls_back_to_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Leitura local é o código desta geração: resposta correta, sem daemon."""
        from steamzero.cli import main as cli

        domain, action = self._arrange(monkeypatch, mutation=False)
        assert cli._try_daemon(domain, action, [], "corr-2") is None


class TestCliDegradesReadOnAmbiguousTransport:
    """BUG-01: timeout do transporte virou E-API-CONTRACT na tela principal.

    Um round-trip interrompido (timeout, resposta ausente, resultado tipado
    inválido) é ``CoreAmbiguousResult``: o daemon pode ter executado ou não.
    Leitura não tem efeito — degradar para o caminho local é seguro.
    """

    def _arrange(self, monkeypatch: pytest.MonkeyPatch, *, mutation: bool) -> tuple[str, str]:
        from types import SimpleNamespace

        from steamzero.service import client as mod
        from steamzero.service.methods import CLI_METHODS

        def _ambiguous(*_args: Any, **_kw: Any) -> None:
            raise mod.CoreAmbiguousResult("resultado da chamada é ambíguo")

        monkeypatch.setattr(mod, "verify_generation", lambda **kw: {"sourceCommit": "x"})
        monkeypatch.setattr(mod, "invoke", _ambiguous)
        monkeypatch.delenv("STEAMZERO_NO_DAEMON", raising=False)
        key = ("fake", "acao")
        monkeypatch.setitem(
            CLI_METHODS,
            key,
            SimpleNamespace(
                method="fake.acao",
                mutation=mutation,
                timeout=2.0,
                args_to_params=lambda _a, _c: {},
            ),
        )
        return key

    def test_read_degrades_to_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from steamzero.cli import main as cli

        domain, action = self._arrange(monkeypatch, mutation=False)
        assert cli._try_daemon(domain, action, [], "corr-3") is None

    def test_mutation_never_degrades_on_ambiguity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Repetir localmente uma mutação ambígua produz efeito duplicado."""
        from steamzero.cli import main as cli

        domain, action = self._arrange(monkeypatch, mutation=True)
        result = cli._try_daemon(domain, action, [], "corr-4")
        assert result is not None, "mutação ambígua não pode cair no caminho local"
        envelope, code = result
        assert code == cli.EXIT_FAILURE
        assert envelope["error"]["code"] == "E-API-CONTRACT"
        assert "ambíguo" in envelope["error"]["detail"]


class TestCliFrontendsFollowSharedDaemonPolicy:
    """As mutações de frontends herdam a política comum do transporte."""

    def _ambiguous(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from steamzero.service import client as mod

        def _ambiguous(*_args: Any, **_kw: Any) -> None:
            raise mod.CoreAmbiguousResult("resultado da chamada é ambíguo")

        monkeypatch.setattr(mod, "verify_generation", lambda **kw: {"sourceCommit": "x"})
        monkeypatch.setattr(mod, "invoke", _ambiguous)
        monkeypatch.delenv("STEAMZERO_NO_DAEMON", raising=False)

    def test_frontends_apply_never_degrades_on_ambiguity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from steamzero.cli import main as cli

        self._ambiguous(monkeypatch)
        result = cli._try_daemon(
            "frontends", "apply", ["--plan-id", "p", "--confirm", "t"], "corr-5"
        )
        assert result is not None, "mutação ambígua não pode cair no caminho local"
        envelope, code = result
        assert code == cli.EXIT_FAILURE
        assert envelope["error"]["code"] == "E-API-CONTRACT"
        assert "ambíguo" in envelope["error"]["detail"]

    def test_frontends_rollback_never_degrades_on_ambiguity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from steamzero.cli import main as cli

        self._ambiguous(monkeypatch)
        result = cli._try_daemon("frontends", "rollback", ["--operation-id", "op"], "corr-6")
        assert result is not None
        envelope, code = result
        assert code == cli.EXIT_FAILURE
        assert envelope["error"]["code"] == "E-API-CONTRACT"

    def test_frontends_verify_read_degrades_to_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from steamzero.cli import main as cli

        self._ambiguous(monkeypatch)
        assert cli._try_daemon("frontends", "verify", ["--spec-json", "{}"], "corr-7") is None


class TestCliNeverDegradesSecurityRefusal:
    """Socket inseguro não é ausência de daemon: é condição de segurança.

    Recusa de segurança NUNCA degrada, nem leitura — degradar esconderia um
    socket substituído (symlink/ownership alheio) atrás de um resultado local.
    """

    def _arrange(self, monkeypatch: pytest.MonkeyPatch, *, in_handshake: bool) -> tuple[str, str]:
        from types import SimpleNamespace

        from steamzero.service import client as mod
        from steamzero.service.methods import CLI_METHODS

        def _refuse(*_args: Any, **_kw: Any) -> None:
            raise mod.CoreSecurityRefusal("socket local possui ownership ou permissões inseguras")

        monkeypatch.setattr(
            mod,
            "verify_generation",
            _refuse if in_handshake else lambda **kw: {"sourceCommit": "x"},
        )
        monkeypatch.setattr(mod, "invoke", _refuse)
        monkeypatch.delenv("STEAMZERO_NO_DAEMON", raising=False)
        key = ("fake", "acao")
        monkeypatch.setitem(
            CLI_METHODS,
            key,
            SimpleNamespace(
                method="fake.acao",
                mutation=False,
                timeout=2.0,
                args_to_params=lambda _a, _c: {},
            ),
        )
        return key

    @pytest.mark.parametrize("in_handshake", [False, True])
    def test_security_refusal_never_degrades_even_for_reads(
        self, monkeypatch: pytest.MonkeyPatch, in_handshake: bool
    ) -> None:
        from steamzero.cli import main as cli

        domain, action = self._arrange(monkeypatch, in_handshake=in_handshake)
        result = cli._try_daemon(domain, action, [], "corr-5")
        assert result is not None, "recusa de segurança não pode degradar"
        envelope, code = result
        assert code == cli.EXIT_FAILURE
        assert envelope["error"]["code"] == "E-API-CONTRACT"
        assert "inseguras" in envelope["error"]["detail"]
