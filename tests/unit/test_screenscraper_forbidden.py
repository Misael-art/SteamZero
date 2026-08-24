# SPDX-License-Identifier: GPL-3.0-or-later
"""G40: um 403 do ScreenScraper nem sempre é cota.

Medido contra a API real em 2026-08-12: o servidor responde HTTP 403 com
``Erreur de login`` quando o problema é credencial ou parâmetro. O cliente
classificava todo 403 como ``E-SCRAPE-QUOTA-EXCEEDED``, e a mensagem mandava o
usuário investigar cota enquanto a causa era outra.

A classificação passou a ler o texto que o próprio servidor devolveu, em vez de
adivinhar a chave da mensagem no payload — que não está documentada no
repositório. Sem marcador de credencial, o comportamento anterior permanece:
reclassifica só com evidência positiva.
"""

from __future__ import annotations

from steamzero.adapters.scraping.screenscraper import _forbidden_code


def test_login_error_is_not_reported_as_quota() -> None:
    assert _forbidden_code("Erreur de login") == "E-SCRAPE-CREDENTIAL-REJECTED"


def test_marker_is_found_regardless_of_which_field_carried_it() -> None:
    """A chave da mensagem não é adivinhada; o texto é varrido venha de onde vier."""
    assert _forbidden_code("403", "Erreur de login") == "E-SCRAPE-CREDENTIAL-REJECTED"
    assert _forbidden_code("403", None, "identifiant incorrect") == ("E-SCRAPE-CREDENTIAL-REJECTED")
    assert _forbidden_code("403", "Mot de passe invalide") == "E-SCRAPE-CREDENTIAL-REJECTED"


def test_quota_without_credential_marker_stays_quota() -> None:
    """Sem evidência de credencial, nada muda — a reclassificação não chuta."""
    assert _forbidden_code("403") == "E-SCRAPE-QUOTA-EXCEEDED"
    assert _forbidden_code("403", "quota depasse") == "E-SCRAPE-QUOTA-EXCEEDED"
    assert _forbidden_code("quota", "trop de requetes aujourd'hui") == ("E-SCRAPE-QUOTA-EXCEEDED")
