# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Autoconfig do RetroArch: leitura, resolução do índice físico e geração.

A G45 parou onde o índice do botão começa. `steamzero.domain.retropad` traduz a
AÇÃO abstrata para a chave RetroPad (`game.primary` → `input_b_btn`), mas o
VALOR dessa chave é um índice que pertence ao dispositivo físico. Inventá-lo
produz um autoconfig plausível e errado — o usuário aperta pular e volta ao
menu.

Este módulo resolve o índice do único jeito honesto disponível: **lendo o
autoconfig que descreve o dispositivo real**. O RetroArch empacota 420 desses
arquivos (`share/libretro/autoconfig/udev/*.cfg`), e cada um é a tabela
"posição física → índice" que o próprio fabricante declarou. Quando não existe
arquivo para o pad conectado, o resultado é NÃO RESOLVIDO e visível — nunca um
palpite.

Três regras deste módulo saíram de medição sobre esses 420 arquivos, não de
memória (contagens com casamento exato de chave, que exclui as linhas
`*_label`):

- **O sufixo pertence ao dispositivo, não à ação.** `input_up_btn` aparece em
  296 arquivos e `input_up_axis` em 134. Fixar `_axis` para direcional — como a
  tradução abstrata faz na ausência de dispositivo — erraria a MAIORIA dos pads
  reais, e sufixo errado gera perfil que o RetroArch aceita e IGNORA: falha
  silenciosa, o pior resultado possível. Por isso o sufixo efetivo é copiado do
  arquivo do dispositivo.
- **O valor não é um número.** 239 arquivos usam notação de hat (`h0up`), e há
  sinal significativo (`-0` e `+0` são entradas OPOSTAS). O valor é tratado como
  token opaco e copiado literalmente; convertê-lo para `int` perderia o sinal de
  `-0` e quebraria `h0up`.
- **O dispositivo sabe dizer "não tenho isso".** 44 arquivos gravam `nul` e 27
  gravam string vazia. Isso é ausência declarada, não valor.

Doze arquivos declaram btn E axis para o mesmo direcional. Escolher um seria
adivinhar qual controle físico o usuário quer; esses ficam explicitamente
ambíguos e não são gravados.

O módulo é PURO: não lê nem escreve disco. Descoberta de dispositivo e gravação
são do adapter.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from steamzero.core.errors import SteamZeroError
from steamzero.domain import retropad

#: Marcador de propriedade (AGENTS.md §5). Arquivo sem ele NUNCA é reescrito nem
#: removido: pertence ao usuário ou ao RetroArch. `#` é comentário no formato —
#: os próprios arquivos empacotados usam essa sintaxe.
MANAGED_MARKER = "# SteamZero-Managed: true"

#: Gramática fechada dos valores que o RetroArch aceita numa chave de binding.
#: Deriva dos 420 arquivos reais: índice com sinal opcional (`0`, `+2`, `-0`) ou
#: hat (`h0up`). Fecha contra lixo upstream — dois arquivos gravam `"ZR Button"`
#: no lugar do índice, e copiar isso geraria um autoconfig inválido.
_VALUE_TOKEN = re.compile(r"\A(?:[+-]?\d+|h\d+(?:up|down|left|right))\Z")

#: Ausência DECLARADA pelo dispositivo. Não é valor e não vira binding.
_UNBOUND = frozenset({"", "nul"})

_SUFFIXES = ("btn", "axis")

#: Ordem canônica de escrita. Determinismo é requisito de idempotência: o mesmo
#: dispositivo e o mesmo perfil precisam gerar bytes idênticos, senão toda
#: verificação regrava o arquivo.
_SLOT_ORDER = (
    "b",
    "a",
    "y",
    "x",
    "select",
    "start",
    "up",
    "down",
    "left",
    "right",
    "l",
    "r",
)

# Motivos de não resolução. Códigos estáveis (a UI e os testes dependem deles);
# o rótulo é o que a tela mostra.
REASON_LABELS: dict[str, str] = {
    "entrada-sem-slot-retropad": "A entrada do perfil não existe no RetroPad.",
    "dispositivo-nao-declara": "O controle conectado não declara essa entrada.",
    "dispositivo-declara-sem-atribuicao": "O controle declara essa entrada como não atribuída.",
    "dispositivo-declara-btn-e-axis": (
        "O controle declara botão e eixo para essa entrada; qual usar seria palpite."
    ),
    "valor-do-dispositivo-ilegivel": "O valor declarado pelo controle não é um índice válido.",
}


@dataclass(frozen=True)
class DeviceIdentity:
    """Identidade real de um pad conectado, lida do host (nunca inferida)."""

    name: str
    vendor_id: int | None = None
    product_id: int | None = None

    def matches(self, autoconfig: Autoconfig) -> bool:
        """Casa identidade com autoconfig.

        Vendor+product é a evidência forte e vem primeiro: é o que o próprio
        RetroArch grava (`input_vendor_id = "10462"`, em DECIMAL — o sysfs
        publica hexadecimal, e a conversão é do adapter). Nome exato é o
        fallback para os arquivos que não declaram os ids.
        """
        if (
            self.vendor_id is not None
            and self.product_id is not None
            and autoconfig.vendor_id is not None
            and autoconfig.product_id is not None
        ):
            return (self.vendor_id, self.product_id) == (
                autoconfig.vendor_id,
                autoconfig.product_id,
            )
        return bool(autoconfig.device_name) and autoconfig.device_name == self.name


@dataclass(frozen=True)
class Autoconfig:
    """Um arquivo de autoconfig já interpretado."""

    entries: Mapping[str, str]
    managed: bool = False

    @property
    def device_name(self) -> str:
        return self.entries.get("input_device", "")

    @property
    def display_name(self) -> str:
        return self.entries.get("input_display_name", "")

    @property
    def driver(self) -> str:
        return self.entries.get("input_driver", "")

    @property
    def vendor_id(self) -> int | None:
        return _as_id(self.entries.get("input_vendor_id"))

    @property
    def product_id(self) -> int | None:
        return _as_id(self.entries.get("input_product_id"))


def _as_id(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def parse_autoconfig(text: str) -> Autoconfig:
    """Interpreta um autoconfig sem executar nada nem confiar no conteúdo.

    Formato observado nos arquivos reais: `chave = "valor"`, comentário com `#`,
    aspas opcionais e espaçamento livre. Linha que não casa é IGNORADA em vez de
    derrubar a leitura — o arquivo é de terceiro e um campo novo do RetroArch
    não pode quebrar a resolução do resto (AGENTS.md §8).
    """
    entries: dict[str, str] = {}
    managed = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            if stripped == MANAGED_MARKER:
                managed = True
            continue
        key, separator, value = stripped.partition("=")
        if not separator:
            continue
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        entries[key] = value
    return Autoconfig(entries=entries, managed=managed)


def is_managed(text: str) -> bool:
    """Verdadeiro só se o marcador de propriedade estiver presente."""
    return any(line.strip() == MANAGED_MARKER for line in text.splitlines())


@dataclass(frozen=True)
class ResolvedBinding:
    """Uma ação cujo índice físico foi LIDO do dispositivo."""

    action: str
    input: str
    key: str
    value: str

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "input": self.input, "key": self.key, "value": self.value}


@dataclass(frozen=True)
class UnresolvedBinding:
    """Uma ação que não pôde ser resolvida, com o motivo dito por extenso."""

    action: str
    input: str
    reason: str

    @property
    def label(self) -> str:
        return REASON_LABELS[self.reason]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "input": self.input,
            "reason": self.reason,
            "reasonLabel": self.label,
        }


@dataclass(frozen=True)
class Resolution:
    """O que vai ser gravado, o que não vai, e por quê."""

    state: str  # resolved | partial | unresolved
    resolved: tuple[ResolvedBinding, ...]
    unresolved: tuple[UnresolvedBinding, ...]
    without_equivalent: tuple[str, ...]

    @property
    def writable(self) -> bool:
        """Só há o que gravar se ao menos uma ação resolveu de verdade."""
        return bool(self.resolved)


def resolve(bindings: Sequence[Mapping[str, Any]], autoconfig: Autoconfig) -> Resolution:
    """Resolve bindings abstratos contra o autoconfig do dispositivo real.

    A chave gravada vem da AÇÃO (`game.primary` → `b`); o sufixo e o valor vêm
    da ENTRADA lida no dispositivo (`button.south` → slot `b` do arquivo →
    `input_b_btn = "0"`). É por isso que um perfil que remapeia funciona: se o
    perfil manda `game.primary` na posição leste, grava-se `input_b_btn` com o
    índice que o dispositivo declarou para leste — índice lido, nunca inventado.
    """
    resolved: list[ResolvedBinding] = []
    unresolved: list[UnresolvedBinding] = []
    without_equivalent = retropad.untranslatable(bindings)
    ignored = set(without_equivalent)

    seen: set[str] = set()
    for binding in bindings:
        action = str(binding.get("action") or "")
        entrada = str(binding.get("input") or "")
        if not action or not entrada:
            raise SteamZeroError("E-API-SCHEMA", detail="binding sem ação ou entrada")
        if action in seen:
            raise SteamZeroError("E-API-SCHEMA", detail=f"ação duplicada: {action}")
        seen.add(action)
        if action in ignored:
            continue

        try:
            input_slot = retropad.retropad_slot(entrada)
        except SteamZeroError:
            unresolved.append(UnresolvedBinding(action, entrada, "entrada-sem-slot-retropad"))
            continue

        found = [
            (suffix, autoconfig.entries[f"input_{input_slot}_{suffix}"])
            for suffix in _SUFFIXES
            if f"input_{input_slot}_{suffix}" in autoconfig.entries
        ]
        usable = [(suffix, value) for suffix, value in found if value.strip() not in _UNBOUND]
        if not found:
            unresolved.append(UnresolvedBinding(action, entrada, "dispositivo-nao-declara"))
            continue
        if not usable:
            unresolved.append(
                UnresolvedBinding(action, entrada, "dispositivo-declara-sem-atribuicao")
            )
            continue
        if len(usable) > 1:
            unresolved.append(UnresolvedBinding(action, entrada, "dispositivo-declara-btn-e-axis"))
            continue
        suffix, value = usable[0]
        if not _VALUE_TOKEN.match(value):
            unresolved.append(UnresolvedBinding(action, entrada, "valor-do-dispositivo-ilegivel"))
            continue
        resolved.append(
            ResolvedBinding(
                action=action,
                input=entrada,
                key=f"input_{retropad.action_slot(action)}_{suffix}",
                value=value,
            )
        )

    if resolved and not unresolved:
        state = "resolved"
    elif resolved:
        state = "partial"
    else:
        state = "unresolved"
    return Resolution(
        state=state,
        resolved=tuple(resolved),
        unresolved=tuple(unresolved),
        without_equivalent=without_equivalent,
    )


def render_managed(
    resolution: Resolution,
    *,
    identity: DeviceIdentity,
    source: Autoconfig,
    profile_id: str,
    profile_revision: int,
    orientation: str,
) -> str:
    """Gera o autoconfig gerenciado, determinístico e auto-explicativo.

    Determinismo não é estética: sem ele, cada verificação regravaria o arquivo
    e a operação deixaria de ser idempotente.
    """
    if not resolution.writable:
        raise SteamZeroError(
            "E-COMPONENT-DEGRADED",
            detail="nenhum binding resolvido: não há autoconfig honesto a gravar",
        )
    lines = [
        MANAGED_MARKER,
        f"# Perfil SteamZero {profile_id} rev {profile_revision}, orientação {orientation}.",
        "# Arquivo gerado. Remova a primeira linha para assumir a propriedade dele;",
        "# enquanto ela existir, o SteamZero pode reescrever este arquivo.",
        "",
    ]
    driver = source.driver or "udev"
    lines.append(f'input_driver = "{driver}"')
    lines.append(f'input_device = "{identity.name}"')
    if identity.vendor_id is not None:
        lines.append(f'input_vendor_id = "{identity.vendor_id}"')
    if identity.product_id is not None:
        lines.append(f'input_product_id = "{identity.product_id}"')
    lines.append("")

    order = {slot: index for index, slot in enumerate(_SLOT_ORDER)}
    for binding in sorted(
        resolution.resolved,
        key=lambda item: (order.get(retropad.action_slot(item.action), len(order)), item.key),
    ):
        lines.append(f'{binding.key} = "{binding.value}"')
    for missing in sorted(resolution.unresolved, key=lambda item: item.action):
        lines.append(f"# {missing.action} não resolvido: {missing.label}")
    for action in resolution.without_equivalent:
        lines.append(f"# {action} não tem equivalente RetroPad.")
    return "\n".join(lines) + "\n"
