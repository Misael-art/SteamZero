# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""G37 — o preview do editor percorre a cadeia ``extends``.

Antes, `_make_resolved` montava o preview só com os tokens da sessão. Um tema
novo que estendia `org.steamzero.aura` aparecia com a paleta PADRÃO, não com a
herdada — o usuário escolhia uma base e via outra coisa, sem nada indicando o
descompasso.

Os valores conferidos aqui foram medidos nos builtins, não escolhidos:

    org.steamzero.default    accent #006f99   background #e7eceb
    org.steamzero.aura       accent #22d3ee   background #0b1020
    org.steamzero.steamdeck  accent #1b9e4a   background #e7eceb

Duas bases distintas produzindo o MESMO preview é a assinatura do defeito, e é
por isso que os testes comparam bases entre si em vez de afirmar uma cor
isolada: uma asserção de cor única passaria mesmo com a herança desligada.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from steamzero.core import paths
from steamzero.core.errors import SteamZeroError
from steamzero.domain.theme_editor import ThemeEditorManager

DEFAULT_ID = "org.steamzero.default"
AURA_ID = "org.steamzero.aura"
DECK_ID = "org.steamzero.steamdeck"


def _colors(preview: dict[str, Any]) -> dict[str, Any]:
    return dict(preview["resolved"]["color"])


def _preview_for(extends: str) -> dict[str, Any]:
    return _colors(ThemeEditorManager().create(f"Tema {extends}", extends=extends)["preview"])


def _write_theme(root: Path, theme_id: str, *, extends: str | None, accent: str) -> None:
    """Grava um tema de usuário mínimo para montar cadeias controladas."""
    directory = root / theme_id
    directory.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "id": theme_id,
        "name": theme_id,
        "version": "1.0.0",
        "author": "teste",
        "license": "MIT",
        "tokens": {"color": {"accent": accent}},
    }
    if extends is not None:
        manifest["extends"] = extends
    (directory / "theme.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.fixture
def themes_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Diretório de temas do usuário isolado.

    Sem isto, um tema de teste vazaria para o estado real do operador — e a
    suíte passaria a depender do que já existe na máquina de quem roda.
    """
    root = tmp_path / "themes"
    root.mkdir()
    monkeypatch.setattr(paths, "themes_dir", lambda: root)
    return root


class TestThePreviewInheritsFromTheChosenBase:
    def test_extending_the_default_yields_the_default_palette(self) -> None:
        colors = _preview_for(DEFAULT_ID)
        assert colors["accent"] == "#006f99"
        assert colors["background"] == "#e7eceb"

    def test_extending_aura_yields_the_aura_palette(self) -> None:
        """O caso exato do G37: escolher AURA e ver AURA."""
        colors = _preview_for(AURA_ID)
        assert colors["accent"] == "#22d3ee"
        assert colors["background"] == "#0b1020"

    def test_two_different_bases_never_produce_the_same_preview(self) -> None:
        """A asserção que pega o defeito.

        Uma cor isolada passaria mesmo com a herança desligada, porque o
        fallback devolve a paleta padrão. Comparar bases entre si não passa.
        """
        default = _preview_for(DEFAULT_ID)
        aura = _preview_for(AURA_ID)
        deck = _preview_for(DECK_ID)
        assert default != aura
        assert default != deck
        assert aura != deck

    def test_the_session_tokens_win_over_the_inherited_ones(self, themes_dir: Path) -> None:
        """Herdar não pode apagar o que o usuário acabou de editar."""
        manager = ThemeEditorManager()
        session = manager.create("Sobrescreve", extends=AURA_ID)
        result = manager.set_tokens(str(session["sessionId"]), "color", {"accent": "#ff00ff"})
        colors = _colors(result["preview"])
        assert colors["accent"] == "#ff00ff"
        # E o que NÃO foi editado continua vindo da base.
        assert colors["background"] == "#0b1020"


class TestChainsAndTheirLimits:
    def test_the_deepest_allowed_chain_resolves(self, themes_dir: Path) -> None:
        """Sessão → builtin → default é o mais fundo que `MAX_EXTENDS_DEPTH = 2`
        permite, e precisa resolver por inteiro."""
        colors = _preview_for(AURA_ID)
        assert colors["accent"] == "#22d3ee"
        assert colors["background"] == "#0b1020"

    def test_a_chain_beyond_the_depth_limit_degrades(self, themes_dir: Path) -> None:
        """Um tema de usuário que estende OUTRO tema de usuário excede o limite.

        Medido: `MAX_EXTENDS_DEPTH = 2`, e a sessão já ocupa o nível 0. A cadeia
        sessão → folha → meio → aura → default chega a 4 e é recusada pelo
        resolver, então o preview degrada.

        O teste congela isso como comportamento CONHECIDO, não desejável: o
        usuário escolhe uma base e vê a paleta padrão, sem nada dizendo que a
        cadeia foi longa demais. É a mesma forma do G37, um nível acima —
        registrado como G39.
        """
        _write_theme(themes_dir, "org.teste.meio", extends=AURA_ID, accent="#111111")
        _write_theme(themes_dir, "org.teste.folha", extends="org.teste.meio", accent="#222222")

        colors = _preview_for("org.teste.folha")
        assert colors["accent"] == "#006f99", (
            "cadeia acima do limite cai na paleta padrão — silenciosamente"
        )

    def test_a_cycle_degrades_instead_of_hanging(self, themes_dir: Path) -> None:
        """Ciclo é erro do autor do tema, não motivo para travar o editor.

        `ThemeResolver` detecta e levanta; `_make_resolved` degrada para os
        tokens da sessão. O preview fica pobre, mas responde — e o editor
        continua utilizável.
        """
        _write_theme(themes_dir, "org.teste.a", extends="org.teste.b", accent="#aaaaaa")
        _write_theme(themes_dir, "org.teste.b", extends="org.teste.a", accent="#bbbbbb")

        colors = _preview_for("org.teste.a")
        assert colors, "o preview não pode vir vazio"
        assert "accent" in colors

    def test_a_missing_base_degrades_to_the_session_tokens(self) -> None:
        colors = _preview_for("org.nao.existe")
        assert colors["accent"] == "#006f99", "degrada para a resolução sem herança"

    def test_a_corrupt_theme_on_disk_does_not_break_the_preview(self, themes_dir: Path) -> None:
        """Um `theme.json` ilegível no diretório do usuário é dado, não código.

        Ele não pode impedir o editor de abrir — só de participar da cadeia.
        """
        broken = themes_dir / "org.teste.quebrado"
        broken.mkdir()
        (broken / "theme.json").write_text("{ isto não é json", encoding="utf-8")

        colors = _preview_for(AURA_ID)
        assert colors["accent"] == "#22d3ee", "a cadeia sã continua resolvendo"


class TestTheEditorNeverMutatesWhatItReads:
    """Resolver a cadeia obriga a LER builtins e temas do usuário.

    Ler é o que a correção precisa; escrever seria efeito colateral, e o preview
    é uma operação de leitura por contrato.
    """

    def test_previewing_does_not_write_to_the_themes_directory(self, themes_dir: Path) -> None:
        _write_theme(themes_dir, "org.teste.base", extends=AURA_ID, accent="#333333")
        before = {
            path: path.read_bytes() for path in sorted(themes_dir.rglob("*")) if path.is_file()
        }

        manager = ThemeEditorManager()
        session = manager.create("Somente preview", extends="org.teste.base")
        manager.preview(str(session["sessionId"]))
        manager.preview(str(session["sessionId"]), high_contrast=True)

        after = {
            path: path.read_bytes() for path in sorted(themes_dir.rglob("*")) if path.is_file()
        }
        assert after == before, "o preview escreveu no diretório de temas"

    def test_cancelling_discards_the_session_without_touching_disk(self, themes_dir: Path) -> None:
        manager = ThemeEditorManager()
        session = manager.create("Descartável", extends=AURA_ID)
        session_id = str(session["sessionId"])
        manager.set_tokens(session_id, "color", {"accent": "#ff0000"})

        manager.cancel(session_id)

        assert not list(themes_dir.iterdir()), "cancelar não pode deixar tema em disco"
        # Exceção ESPECÍFICA: `pytest.raises(Exception)` passaria com qualquer
        # erro, inclusive um `AttributeError` de refactor mal feito — e o teste
        # deixaria de provar que a sessão foi de fato descartada.
        with pytest.raises(SteamZeroError, match="sessão não encontrada"):
            manager.preview(session_id)
