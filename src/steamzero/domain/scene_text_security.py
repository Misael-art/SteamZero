# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Sanitização do único formato rico permitido pela cena.

``Text.StyledText`` aceita uma pequena linguagem de marcação. O texto do tema
é dado externo, portanto passá-lo diretamente como ``RichText`` permitiria
atributos, imagens e URLs que não fazem parte do contrato visual do SteamZero.
Esta fronteira conserva somente as quatro tags sem atributos que o contrato
declara e escapa todo texto literal.
"""

from __future__ import annotations

import html
from html.parser import HTMLParser

_ALLOWED_TAGS = frozenset({"b", "i", "u", "br"})


class _StyledTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.changed = False
        self._open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in _ALLOWED_TAGS and not attrs:
            self.parts.append(f"<{normalized}>")
            if normalized != "br":
                self._open_tags.append(normalized)
            return
        self.changed = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized == "br" and not attrs:
            self.parts.append("<br>")
            return
        self.changed = True

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in _ALLOWED_TAGS and normalized != "br" and normalized in self._open_tags:
            while self._open_tags and self._open_tags[-1] != normalized:
                self.parts.append(f"</{self._open_tags.pop()}>")
                self.changed = True
            self.parts.append(f"</{self._open_tags.pop()}>")
            return
        if normalized != "br":
            self.changed = True

    def handle_data(self, data: str) -> None:
        self.parts.append(html.escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.changed = True

    def handle_decl(self, decl: str) -> None:
        self.changed = True

    def handle_pi(self, data: str) -> None:
        self.changed = True


def sanitize_styled_text(value: str) -> tuple[str, bool]:
    """Retorna ``(texto, alterado)`` em uma gramática rica allowlisted.

    A função é idempotente para que o adapter possa revalidar um DTO
    desserializado sem produzir diferenças adicionais.
    """
    parser = _StyledTextParser()
    parser.feed(value)
    parser.close()
    while parser._open_tags:
        parser.parts.append(f"</{parser._open_tags.pop()}>")
        parser.changed = True
    return "".join(parser.parts), parser.changed
