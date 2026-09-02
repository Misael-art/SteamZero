# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Tradução biblioteca canônica -> home do AURA Launcher.

O catálogo que a home mostra deve ser o conteúdo BASE, com o rótulo exibível
correto (``name``, nunca o id) e agrupado por plataforma. Um algoritmo que
perde essas três coisas devolve uma home que abre, mas que não serve.
"""

from __future__ import annotations

from steamzero.adapters.launcher_catalog import catalog_games, catalog_summary


def test_base_games_are_listed_with_the_canonical_label() -> None:
    games = catalog_games(
        [
            {"id": "a1", "name": "1969 (Homebrew) (SMS)", "platform": "master-system"},
            {"id": "b2", "name": "Ridge Racer", "platform": "playstation"},
        ]
    )
    assert [g.title for g in games] == ["1969 (Homebrew) (SMS)", "Ridge Racer"]
    assert [g.platform for g in games] == ["master-system", "playstation"]


def test_update_and_dlc_are_excluded() -> None:
    """Update/DLC são conteúdo real, mas `launch_game` os recusa: oferecê-los
    produziria um erro que o usuário não teria como prever olhando a tela."""
    games = catalog_games(
        [
            {"id": "base", "name": "Base", "contentKind": "base", "platform": "switch"},
            {"id": "upd", "name": "Update", "contentKind": "update", "platform": "switch"},
            {"id": "dlc", "name": "DLC", "contentKind": "dlc", "platform": "switch"},
        ]
    )
    assert [g.id for g in games] == ["base"]


def test_title_fallback_never_shows_the_identifier() -> None:
    """A biblioteca canônica publica o rótulo em `name`; o fallback para o id
    fazia a home exibir `ae18c7e53583298461a0edea` no lugar de um título."""
    games = catalog_games([{"id": "ae18c7e53583298461a0edea", "name": "1969 (Homebrew) (SMS)"}])
    assert games[0].title == "1969 (Homebrew) (SMS)"


def test_a_broken_record_does_not_clear_the_home() -> None:
    """Um registro corrompido (sem id ou sem rótulo) é descartado; os demais
    permanecem — a home não pode esvaziar por causa de uma entrada ruim."""
    games = catalog_games(
        [
            {"id": "", "name": "sem id"},
            {"id": "ok", "name": "Válido", "platform": "snes"},
            {"id": "sem-nome"},
        ]
    )
    assert [g.id for g in games] == ["ok"]


def test_platform_is_derived_for_switch_formats() -> None:
    """Formato de ROM Switch sem `platform` mapeia para `switch`; formato
    desconhecido cai na extensão normalizada."""
    games = catalog_games(
        [
            {"id": "nsp", "name": "NSP", "format": "NSP"},
            {"id": "gb", "name": "GB", "format": "gb"},
        ]
    )
    assert [g.platform for g in games] == ["switch", "gb"]


class TestSummaryNeverInventsADenominator:
    """`filesFound` não pode ser preenchido com o número de jogos.

    Medido em 2026-09-02 contra o cache canônico real do host: o envelope não
    tinha `scanSummary` (foi gravado antes do campo existir) e o resumo
    publicava `filesFound: 231, ignored: 0, incompatible: 0` — enquanto o
    `rootStats` do MESMO arquivo registrava 6724 ignorados e 1061
    incompatíveis. A home renderiza esse resumo, então a UI afirmaria "231
    arquivos encontrados, 231 jogos, 0 para revisão" com ar de fato, que é o
    oposto do que a reconciliação existe para explicar.
    """

    def _game(self, identifier: str) -> dict[str, object]:
        return {"id": identifier, "name": identifier, "platform": "nes-famicom"}

    def test_an_envelope_without_a_scan_summary_reads_the_root_stats(self) -> None:
        records = [self._game("a"), self._game("b")]
        payload = {
            "games": records,
            "rootStats": {
                "root-1": {
                    "counts": {
                        "base": 2,
                        "updates": 3,
                        "dlcs": 4,
                        "incompatible": 10,
                        "ignored": 20,
                        "errors": 1,
                    }
                }
            },
        }
        catalog = catalog_games(records)
        summary = catalog_summary(payload, catalog, records)
        assert summary["ignored"] == 20, "a verdade estava no mesmo arquivo"
        assert summary["incompatible"] == 10
        assert summary["updates"] == 3
        assert summary["dlcs"] == 4

    def test_a_summaryless_payload_does_not_claim_a_file_count(self) -> None:
        records = [self._game("a"), self._game("b")]
        catalog = catalog_games(records)
        summary = catalog_summary(None, catalog, records)
        assert "filesFound" not in summary, (
            "sem contagem de arquivos o resumo deve omitir o campo; preenchê-lo "
            "com o número de jogos afirma que todo arquivo virou jogo"
        )

    def test_the_file_count_is_not_rebuilt_by_adding_buckets(self) -> None:
        """Somar os baldes não fecha com o disco.

        No acervo real a soma dá 8381 para 8016 arquivos e 202 symlinks — 163 a
        mais, exatamente updates+DLCs, que as duas varreduras contam cada uma
        por si. Publicar essa soma seria trocar um número errado por outro.
        """
        records = [self._game("a")]
        payload = {
            "games": records,
            "rootStats": {"root-1": {"counts": {"base": 1, "updates": 5, "ignored": 7}}},
        }
        summary = catalog_summary(payload, catalog_games(records), records)
        assert "filesFound" not in summary
        assert summary["ignored"] == 7
