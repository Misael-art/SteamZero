# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Fronteira de confiança do asset-fonte SVG (frente A2).

Tema de terceiro não alcança rede nem disco (AGENTS.md §10). Cada vetor aqui foi
**provado aceito** por sonda antes da correção; o teste existe para que a brecha
não volte em silêncio.

O que a validação garante é estreito de propósito: um SVG só pode referenciar a
si mesmo (``#fragmento``) ou trazer a imagem embutida (``data:image/...``). O
allowlist é sobre o que o tema PODE alcançar, não sobre o que sabemos ser
perigoso — a lista de esquemas perigosos nunca termina.
"""

from __future__ import annotations

import pathlib

import pytest

from steamzero.domain.asset_recipes import validate_asset_source

_SVG = '<svg xmlns="http://www.w3.org/2000/svg">{}</svg>'


def _svg(body: str) -> bytes:
    return _SVG.format(body).encode("utf-8")


# -- referência externa: vazamento de requisição -----------------------------


@pytest.mark.parametrize(
    "body",
    [
        '<image href="https://rastreador.example/p.png"/>',
        '<image href="http://rastreador.example/p.png"/>',
        '<image xlink:href="https://rastreador.example/p.png"/>',
        '<use href="https://evil.example/x.svg#a"/>',
        '<image src="https://evil.example/p.png"/>',
        '<rect fill="url(https://evil.example/g.svg#grad)"/>',
        '<style>@import url("https://evil.example/x.css");</style>',
        "<style>@IMPORT 'https://evil.example/x.css';</style>",
    ],
)
def test_referencia_externa_e_recusada(body: str) -> None:
    """Renderizar isto vazaria uma requisição do host do usuário."""
    with pytest.raises(ValueError):
        validate_asset_source(_svg(body))


# -- caminho absoluto: leitura de arquivo local ------------------------------


@pytest.mark.parametrize(
    "body",
    [
        '<image href="file:///etc/passwd"/>',
        '<image href="/etc/shadow"/>',
        '<image xlink:href="file:///proc/self/environ"/>',
        '<image href="../../etc/passwd"/>',
        '<image href="media/local.png"/>',
    ],
)
def test_caminho_de_disco_e_recusado(body: str) -> None:
    """Relativo também: dependeria de âncora que o asset não declara, e ``../``
    o transformaria em travessia."""
    with pytest.raises(ValueError):
        validate_asset_source(_svg(body))


# -- data URI: só imagem, nunca SVG aninhado ---------------------------------


def test_svg_aninhado_em_data_uri_e_recusado() -> None:
    """SVG dentro de data URI não passaria por esta validação — é exatamente a
    porta que ela fecha."""
    with pytest.raises(ValueError):
        validate_asset_source(_svg('<image href="data:image/svg+xml;base64,PHN2Zy8+"/>'))


@pytest.mark.parametrize("mime", ["text/html", "application/javascript", "text/xml"])
def test_data_uri_de_tipo_nao_imagem_e_recusado(mime: str) -> None:
    with pytest.raises(ValueError):
        validate_asset_source(_svg(f'<image href="data:{mime};base64,AAAA"/>'))


@pytest.mark.parametrize("mime", ["image/png", "image/jpeg", "image/webp", "image/gif"])
def test_imagem_embutida_e_aceita(mime: str) -> None:
    validate_asset_source(_svg(f'<image href="data:{mime};base64,iVBORw0KGgo="/>'))


# -- o que precisa continuar funcionando -------------------------------------


def test_fragmento_interno_e_aceito() -> None:
    """Gradiente e clipPath por ``#id`` são o uso normal — recusá-los quebraria
    todo SVG legítimo do projeto."""
    validate_asset_source(_svg('<use href="#grad1"/><rect fill="url(#a)"/>'))


def test_svg_sem_nenhuma_referencia_e_aceito() -> None:
    validate_asset_source(_svg('<rect width="10" height="10" fill="#ff0000"/>'))


def test_href_vazio_nao_derruba_a_validacao() -> None:
    validate_asset_source(_svg('<use href=""/>'))


# -- conteúdo ativo: guarda pré-existente, mantida ---------------------------


@pytest.mark.parametrize(
    "body",
    ["<script>alert(1)</script>", "<foreignObject><b>x</b></foreignObject>"],
)
def test_conteudo_ativo_continua_recusado(body: str) -> None:
    with pytest.raises(ValueError, match="conteúdo ativo"):
        validate_asset_source(_svg(body))


def test_event_handler_continua_recusado() -> None:
    with pytest.raises(ValueError, match="event handler"):
        validate_asset_source(b'<svg onload="x()"></svg>')


# -- regressão contra os assets reais do projeto -----------------------------

_ASSETS = pathlib.Path(__file__).resolve().parents[2] / "src" / "steamzero" / "ui" / "assets"


def test_assets_reais_do_projeto_nao_sao_recusados_pela_regra_de_referencia() -> None:
    """A regra nova não pode reprovar arte legítima já empacotada.

    Três assets do projeto (``mega-drive``, ``nintendo-handheld``,
    ``playstation-3``) já eram recusados ANTES desta mudança, por conterem
    ``<!DOCTYPE`` — guarda pré-existente de conteúdo ativo. Eles não passam pelo
    validador em produção, porque este valida pacote de tema de terceiro e não
    ícone first-party carregado direto pelo QML. O teste fixa o escopo: nenhum
    asset pode ser reprovado pela regra NOVA (referência externa).
    """
    conhecidos = {"mega-drive.svg", "nintendo-handheld.svg", "playstation-3.svg"}
    svgs = sorted(_ASSETS.glob("*.svg"))
    assert svgs, f"nenhum SVG em {_ASSETS}"

    for path in svgs:
        try:
            validate_asset_source(path.read_bytes())
        except ValueError as exc:
            assert path.name in conhecidos, f"{path.name} reprovou inesperadamente: {exc}"
            assert "conteúdo ativo" in str(exc), (
                f"{path.name} reprovou pela regra NOVA, não pela pré-existente: {exc}"
            )
