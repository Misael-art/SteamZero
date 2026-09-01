# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato de identificador do AURA Launcher.

O mesmo contrato vivia copiado em cinco expressões, em três módulos. Enquanto
todas concordaram, a duplicação passou despercebida; quando a biblioteca
canônica passou a publicar ids hexadecimais, ela virou o defeito: consertar a
home sem consertar o lançamento deixaria o usuário ver 231 jogos e conseguir
abrir 84. Um contrato que precisa valer em três lugares mora em um.

O que o identificador precisa garantir é que um id atravesse foco, argv e
persistência sem virar outra coisa: nada de `;`, `|`, espaço, barra ou dois
pontos (que separam seção de item no focus id), nada de hífen inicial — que
seria lido como opção de linha de comando — e comprimento limitado.

Começar por dígito nunca ameaçou nada disso. A restrição a letra inicial era
convenção de ids sintéticos (``header:home``, ``empty:action``) aplicada, sem
querer, ao acervo real: os ids canônicos são hexadecimais de 24 caracteres, e
63% deles começam por dígito. Observado no host com 231 jogos, dos quais 147
eram rejeitados.
"""

from __future__ import annotations

import re
from typing import TypeGuard

# Alfanumérico na cabeça, alfanumérico ou hífen no corpo. A assimetria da versão
# anterior — dígito proibido na primeira posição, permitido nas demais — não
# protegia nada que o corpo já não permitisse.
IDENTIFIER_PATTERN = r"[a-zA-Z0-9][a-zA-Z0-9-]{0,63}"

IDENTIFIER = re.compile(rf"^{IDENTIFIER_PATTERN}$")

# Um focus id é `seção:item`. Os dois lados obedecem ao mesmo contrato, e os
# dois pontos continuam sendo o único separador — por isso ele não pode aparecer
# dentro de nenhum dos lados.
FOCUS_ID = re.compile(rf"^{IDENTIFIER_PATTERN}:{IDENTIFIER_PATTERN}$")


def is_identifier(value: object) -> TypeGuard[str]:
    """Diz se ``value`` serve como id de seção, item ou jogo.

    O retorno é ``TypeGuard[str]`` porque a checagem que este helper
    substituiu era ``isinstance(value, str) and ...`` e estreitava o tipo
    para quem viesse depois. Devolver ``bool`` puro tirava esse
    estreitamento e transferia para cada chamador o trabalho de reafirmar
    o que a função já provou.
    """
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def is_focus_id(value: object) -> TypeGuard[str]:
    """Diz se ``value`` serve como id de foco (``seção:item``)."""
    return isinstance(value, str) and FOCUS_ID.fullmatch(value) is not None
