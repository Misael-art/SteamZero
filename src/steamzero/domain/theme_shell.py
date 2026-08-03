# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Shell de entrada: evento de controle → movimento de foco.

A ponte entre o que o usuário aperta e o que a cena faz. O tema decide o
destino do foco (``focus_target`` → ``move_focus``); o shell é quem converte o
evento do controle no vocabulário da navegação e o aplica. Separar as duas
coisas é o que permite trocar o mapeamento (um controle alternativo, uma
remapagem de direção) sem tocar na geometria do grid — e o que permite provar
o mapeamento sem runtime nenhum.

O vocabulário do controle é mínimo e deliberado: as quatro direções. Confirmar
e voltar (A/B) chegam com o controle de seleção; direção é o que o grid
navega, e nada além disso atravessa esta fronteira agora.

``current=None`` significa "a cena acabou de carregar, nada está focado" —
qualquer direção foca o primeiro item, a mesma semântica de ``move_focus``.
"""

from __future__ import annotations

from enum import StrEnum

from steamzero.domain.default_theme import DefaultGridMetrics, default_grid_metrics
from steamzero.domain.grid_navigation import Direction, GridSpec, move_focus


class ControlEvent(StrEnum):
    """O vocabulário de entrada do shell de entrada.

    Nomes estáveis, independentes do dispositivo: o teclado e o controle de
    jogo convergem aqui, e quem mapeia o botão físico para o evento é o
    backend de input — fora do escopo desta entrega.
    """

    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


_CONTROL_TO_DIRECTION = {
    ControlEvent.LEFT: Direction.LEFT,
    ControlEvent.RIGHT: Direction.RIGHT,
    ControlEvent.UP: Direction.UP,
    ControlEvent.DOWN: Direction.DOWN,
}


def map_control(event: ControlEvent) -> Direction:
    """Evento de controle → direção da navegação.

    Recusa o que não conhece: um evento desconhecido virado em direção
    adivinhada moveria o foco para um lugar que ninguém pediu, e o defeito
    sumiria na tela em vez de aparecer no mapeamento.
    """
    try:
        return _CONTROL_TO_DIRECTION[event]
    except KeyError:
        raise ValueError(f"evento de controle desconhecido: {event!r}") from None


def apply_control(
    current: int | None,
    event: ControlEvent,
    metrics: DefaultGridMetrics | None = None,
) -> int:
    """Aplica um evento de controle e devolve a célula focada.

    ``current=None`` foca o primeiro item — o estado da cena que acabou de
    carregar. O retorno nunca é ``None`` neste caminho: a grade tem pelo menos
    uma célula, então ``move_focus`` sempre devolve um índice.
    """
    metrics = metrics or default_grid_metrics()
    spec = GridSpec(columns=metrics.columns, rows=metrics.rows, count=metrics.cell_count)
    direction = map_control(event)
    target = move_focus(current, spec, direction)
    if target is None:  # impossível: GridSpec recusa grade vazia
        raise ValueError("move_focus devolveu None fora de grade vazia")
    return target
