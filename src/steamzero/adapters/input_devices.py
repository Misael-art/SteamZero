# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Descoberta do pad real e gravação do autoconfig gerenciado do RetroArch.

`steamzero.domain.retroarch_autoconfig` sabe resolver e gerar; ele não toca em
disco. Este adapter fornece os dois lados que faltam — a identidade do
dispositivo conectado e o arquivo — e é onde moram todas as recusas.

Três limites que este módulo não atravessa:

- **`retroarch.cfg` é do usuário.** Ele é LIDO (para descobrir onde o RetroArch
  procura perfis) e nunca escrito. Onde o RetroArch lê é decisão dele, não
  nossa.
- **Arquivo sem marcador é de terceiro.** Sem `MANAGED_MARKER` na primeira
  linha, o arquivo pertence ao usuário ou ao RetroArch e não é reescrito nem
  removido — a operação vira `conflito` visível (AGENTS.md §5).
- **Nada aqui bloqueia o emulador.** Qualquer falha termina em estado
  diagnosticável e o RetroArch continua utilizável com os padrões dele
  (AGENTS.md §8).

Sobre `awaiting-emulator`: o enunciado pede cinco estados; este é um sexto, e
existe porque medir o host mostrou um caso que os cinco não cobrem com verdade.
O `retroarch.cfg` deste host NÃO EXISTE — o RetroArch nunca foi executado até
gravar configuração. Sem ele, não há como afirmar em qual diretório o RetroArch
procura perfis de controle, e um arquivo gravado num diretório convencional
seria "materializado" sem ser lido. Chamar isso de `aplicado` seria exatamente o
falso verde que a G45 existe para não repetir.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain import retroarch_autoconfig as autoconfig_mod
from steamzero.domain.retroarch_autoconfig import (
    Autoconfig,
    DeviceIdentity,
    Resolution,
)

#: Nome do arquivo gerenciado. Fixo e único: o SteamZero mantém UM perfil por
#: dispositivo, e um nome derivado do perfil faria cada troca deixar um órfão.
MANAGED_BASENAME = "steamzero.cfg"

_MAX_AUTOCONFIG_BYTES = 128 * 1024

STATE_LABELS: dict[str, str] = {
    "not-configured": "Nenhum perfil de controle selecionado",
    "awaiting-device": "Perfil traduzido; aguardando controle reconhecido",
    "awaiting-emulator": "Perfil traduzido; o RetroArch ainda não diz onde lê perfis",
    "pending-write": "Perfil resolvido; ainda não gravado",
    "partial": "Perfil parcialmente aplicado",
    "applied": "Perfil aplicado",
    "conflict": "Existe um arquivo de controle que não é do SteamZero",
    "unsupported-scope": "Perfil por jogo não é aplicável ao autoconfig, que vale por controle",
}


class InputDevicePort(Protocol):
    """Identidades dos pads conectados. Somente leitura, sempre."""

    def identities(self) -> list[DeviceIdentity]: ...


@dataclass(frozen=True)
class SysfsInputDevices:
    """Lê identidade real de pads no sysfs.

    Os índices nunca saem daqui — só a IDENTIDADE (nome, vendor, product). O
    índice vem do autoconfig do fabricante, que é o único lugar onde ele é dado
    e não adivinhado.
    """

    by_id: Path = Path("/dev/input/by-id")
    sys_class: Path = Path("/sys/class/input")

    def identities(self) -> list[DeviceIdentity]:
        try:
            links = sorted(
                path for path in self.by_id.iterdir() if path.name.endswith("-event-joystick")
            )
        except OSError:
            return []
        found: list[DeviceIdentity] = []
        for link in links:
            identity = self._identity_of(link)
            if identity is not None and identity not in found:
                found.append(identity)
        return found

    def _identity_of(self, link: Path) -> DeviceIdentity | None:
        try:
            event = os.path.basename(os.path.realpath(link))
        except OSError:
            return None
        device = self.sys_class / event / "device"
        name = _read_small(device / "name")
        if not name:
            return None
        # sysfs publica os ids em HEXADECIMAL sem prefixo; o autoconfig do
        # RetroArch grava os mesmos ids em DECIMAL. Converter errado faria a
        # busca não casar nunca e todo pad ficaria "sem autoconfig".
        return DeviceIdentity(
            name=name,
            vendor_id=_read_hex(device / "id" / "vendor"),
            product_id=_read_hex(device / "id" / "product"),
        )


def _read_small(path: Path) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(256).strip()
    except OSError:
        return ""


def _read_hex(path: Path) -> int | None:
    raw = _read_small(path)
    try:
        return int(raw, 16)
    except ValueError:
        return None


@dataclass(frozen=True)
class CatalogMatch:
    """Resultado da busca do autoconfig que descreve o pad."""

    autoconfig: Autoconfig | None
    reason: str  # matched | no-device | ambiguous-device | no-autoconfig | ambiguous-autoconfig
    device: DeviceIdentity | None = None
    candidates: tuple[str, ...] = ()


class AutoconfigCatalog:
    """Os autoconfigs que o RetroArch empacota, lidos como dado de terceiro."""

    def __init__(self, directories: Sequence[Path]) -> None:
        self._directories = tuple(directories)
        # O catálogo empacotado tem 420 arquivos. Relê-los a cada consulta
        # colocaria centenas de `open` no caminho do snapshot da dashboard, que
        # já tem histórico de latência neste projeto. Carrega uma vez por
        # instância; trocar de pad não muda o catálogo, só o casamento.
        self._cache: list[tuple[Path, Autoconfig]] | None = None

    def match(self, identities: Sequence[DeviceIdentity]) -> CatalogMatch:
        if not identities:
            return CatalogMatch(None, "no-device")
        if len(identities) > 1:
            # Dois pads distintos e um perfil só: escolher um seria decidir pelo
            # usuário qual controle vale.
            return CatalogMatch(
                None,
                "ambiguous-device",
                candidates=tuple(sorted(identity.name for identity in identities)),
            )
        identity = identities[0]
        matches = [
            (path, parsed)
            for path, parsed in self._load()
            if identity.matches(parsed) and not parsed.managed
        ]
        if not matches:
            return CatalogMatch(None, "no-autoconfig", device=identity)
        distinct = {tuple(sorted(_binding_entries(parsed).items())) for _path, parsed in matches}
        if len(distinct) > 1:
            # Arquivos diferentes descrevem o mesmo pad de formas diferentes;
            # qualquer escolha aqui seria palpite sobre qual é o certo.
            return CatalogMatch(
                None,
                "ambiguous-autoconfig",
                device=identity,
                candidates=tuple(sorted(path.name for path, _parsed in matches)),
            )
        return CatalogMatch(
            matches[0][1],
            "matched",
            device=identity,
            candidates=(matches[0][0].name,),
        )

    def _load(self) -> list[tuple[Path, Autoconfig]]:
        if self._cache is not None:
            return self._cache
        loaded: list[tuple[Path, Autoconfig]] = []
        for directory in self._directories:
            try:
                entries = sorted(directory.glob("*.cfg"))
            except OSError:
                continue
            for path in entries:
                text = _read_text_limited(path)
                if text is None:
                    continue
                loaded.append((path, autoconfig_mod.parse_autoconfig(text)))
        self._cache = loaded
        return loaded


def _binding_entries(parsed: Autoconfig) -> dict[str, str]:
    return {
        key: value
        for key, value in parsed.entries.items()
        if key.startswith("input_") and (key.endswith("_btn") or key.endswith("_axis"))
    }


def _read_text_limited(path: Path) -> str | None:
    """Leitura tolerante para dados de TERCEIRO que só são consultados.

    Devolver `None` em qualquer problema é adequado aqui — um autoconfig
    ilegível do catálogo simplesmente não entra na busca. NÃO serve para decidir
    gravação: ver `_probe_target`, onde `None` significaria "pode escrever".
    """
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if path.stat().st_size > _MAX_AUTOCONFIG_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


#: Por que um caminho existente NÃO é nosso. Cada motivo é dito ao usuário: um
#: "conflito" sem causa não dá ação nenhuma a quem lê.
FOREIGN_REASONS: dict[str, str] = {
    "symlink": "o caminho é um link simbólico e não foi criado pelo SteamZero",
    "not-regular": "o caminho existe e não é um arquivo regular",
    "oversized": "o arquivo é grande demais para conferir o marcador",
    "unreadable": "o arquivo não pôde ser lido para conferir o marcador",
    "no-marker": "o arquivo não tem o marcador do SteamZero",
}


@dataclass(frozen=True)
class TargetProbe:
    """Classificação do alvo antes de qualquer escrita.

    A regra é deliberadamente pessimista: **só a ausência comprovada (ENOENT)
    autoriza gravar**. Symlink, arquivo especial, arquivo grande demais e
    arquivo ilegível são ESTRANGEIROS, não ausentes.

    A versão anterior usava `_read_text_limited`, que devolve `None` para todos
    esses casos E para o arquivo inexistente. Quem lia o `None` concluía
    "ausente, pode escrever", e um `steamzero.cfg` do usuário que fosse symlink,
    passasse de 128 KiB ou não pudesse ser lido seria substituído sem que o
    marcador jamais fosse conferido — exatamente a garantia que a AGENTS.md §5
    exige e que esta entrega afirma dar.
    """

    kind: str  # absent | managed | foreign
    text: str = ""
    reason: str = ""

    @property
    def detail(self) -> str:
        return FOREIGN_REASONS.get(self.reason, "")


def _probe_target(path: Path) -> TargetProbe:
    """Diz se o alvo é nosso, de terceiro, ou não existe — sem seguir symlink."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return TargetProbe("absent")
    except OSError:
        # Nem `lstat` funcionou: o caminho existe de alguma forma que não
        # conseguimos inspecionar. Tratar como nosso seria a suposição errada.
        return TargetProbe("foreign", reason="unreadable")
    if stat.S_ISLNK(info.st_mode):
        return TargetProbe("foreign", reason="symlink")
    if not stat.S_ISREG(info.st_mode):
        return TargetProbe("foreign", reason="not-regular")
    if info.st_size > _MAX_AUTOCONFIG_BYTES:
        return TargetProbe("foreign", reason="oversized")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return TargetProbe("foreign", reason="unreadable")
    if not autoconfig_mod.is_managed(text):
        return TargetProbe("foreign", reason="no-marker")
    return TargetProbe("managed", text=text)


@dataclass(frozen=True)
class AutoconfigTarget:
    """Onde gravar, e se o RetroArch DISSE que lê dali."""

    directory: Path | None
    declared: bool

    @property
    def path(self) -> Path | None:
        return None if self.directory is None else self.directory / MANAGED_BASENAME


#: Driver de joypad padrão quando o `retroarch.cfg` não declara um. O
#: subdiretório NÃO é decoração: medindo o pacote 1.22.2 instalado, a raiz de
#: `share/libretro/autoconfig` tem ZERO arquivos `.cfg`, e os perfis moram em
#: subdiretórios com o nome do driver (`udev/` com 420, `dinput/` com 223,
#: `sdl2/` com 67...). Gravar na raiz produziria um arquivo que ninguém lê.
_DEFAULT_JOYPAD_DRIVER = "udev"


def _setting(text: str, key: str) -> str:
    for line in text.splitlines():
        name, separator, value = line.strip().partition("=")
        if separator and name.strip() == key:
            return value.strip().strip('"')
    return ""


def resolve_target(config_file: Path, fallback_directory: Path | None = None) -> AutoconfigTarget:
    """Descobre o diretório de perfis LENDO o `retroarch.cfg` — nunca escrevendo.

    Duas coisas medidas no RetroArch 1.22.2 Flatpak instalado neste host, ambas
    fatais se ignoradas:

    **O subdiretório do driver é obrigatório.** O RetroArch procura perfis em
    ``<joypad_autoconfig_dir>/<input_joypad_driver>/``, não na raiz — a raiz do
    pacote tem zero `.cfg` e `udev/` tem 420. Gravar na raiz geraria um arquivo
    que nunca seria lido.

    **O caminho declarado pode ser interno ao sandbox.** O config que o próprio
    RetroArch cria declara ``/app/share/libretro/autoconfig``, e ``/app`` não
    existe no host: é o ponto de montagem somente-leitura do Flatpak. Um
    diretório declarado, portanto, não implica um diretório alcançável — e é por
    isso que `declared` sozinho nunca autoriza dizer "aplicado".
    """
    text = _read_text_limited(config_file)
    if text is not None:
        directory = _setting(text, "joypad_autoconfig_dir")
        if directory:
            driver = _setting(text, "input_joypad_driver") or _DEFAULT_JOYPAD_DRIVER
            expanded = Path(directory).expanduser()
            return AutoconfigTarget(expanded / driver, declared=True)
    return AutoconfigTarget(
        None if fallback_directory is None else fallback_directory / _DEFAULT_JOYPAD_DRIVER,
        declared=False,
    )


#: Onde o RetroArch Flatpak guarda configuração e onde empacota os autoconfigs.
#: São caminhos de LEITURA; o único caminho de escrita é o alvo resolvido.
_FLATPAK_CONFIG = Path(".var/app/org.libretro.RetroArch/config/retroarch")
_FLATPAK_BUNDLED = Path("share/libretro/autoconfig/udev")
_FLATPAK_ROOTS = (
    Path(".local/share/flatpak/app/org.libretro.RetroArch"),
    Path("/var/lib/flatpak/app/org.libretro.RetroArch"),
)


def bundled_autoconfig_directories(home: Path | None = None) -> list[Path]:
    """Diretórios de autoconfig empacotados pelo RetroArch instalado.

    Cobre instalação por usuário e por sistema. Nenhum caminho é criado: o que
    não existir simplesmente não entra, e um host sem RetroArch resulta em
    catálogo vazio — que vira `awaiting-device`, não erro.
    """
    base = home or Path.home()
    found: list[Path] = []
    for root in _FLATPAK_ROOTS:
        absolute = root if root.is_absolute() else base / root
        try:
            candidates = sorted(absolute.glob(f"*/*/active/files/{_FLATPAK_BUNDLED}"))
        except OSError:
            continue
        found.extend(path for path in candidates if path.is_dir())
    return found


def host_controls(
    home: Path | None = None, devices: InputDevicePort | None = None
) -> RetroArchControls:
    """Monta a integração contra os caminhos reais do host, somente leitura.

    Construir isto NÃO grava nada: `status()` apenas observa. A gravação exige
    chamada explícita de `apply()`.
    """
    base = home or Path.home()
    config = base / _FLATPAK_CONFIG
    return RetroArchControls(
        devices=devices or SysfsInputDevices(),
        catalog=AutoconfigCatalog(bundled_autoconfig_directories(base)),
        target=resolve_target(config / "retroarch.cfg", config / "autoconfig"),
    )


@dataclass(frozen=True)
class AutoconfigOutcome:
    """O que o status publica. `applied` só é verdade quando tudo foi provado."""

    state: str
    resolution: Resolution | None
    match: CatalogMatch
    target: AutoconfigTarget
    detail: str = ""

    @property
    def label(self) -> str:
        return STATE_LABELS[self.state]

    def to_dict(self) -> dict[str, Any]:
        resolution = self.resolution
        return {
            "state": self.state,
            "statusLabel": self.label,
            "detail": self.detail,
            "device": (
                None
                if self.match.device is None
                else {
                    "name": self.match.device.name,
                    "vendorId": self.match.device.vendor_id,
                    "productId": self.match.device.product_id,
                }
            ),
            "deviceReason": self.match.reason,
            "autoconfigCandidates": list(self.match.candidates),
            "path": None if self.target.path is None else str(self.target.path),
            "directoryDeclared": self.target.declared,
            "resolvedBindings": (
                [] if resolution is None else [item.to_dict() for item in resolution.resolved]
            ),
            "unresolvedBindings": (
                [] if resolution is None else [item.to_dict() for item in resolution.unresolved]
            ),
            "withoutRetropadEquivalent": (
                [] if resolution is None else list(resolution.without_equivalent)
            ),
        }


class RetroArchControls:
    """Junta pad real, autoconfig do fabricante e arquivo gerenciado."""

    def __init__(
        self,
        *,
        devices: InputDevicePort,
        catalog: AutoconfigCatalog,
        target: AutoconfigTarget,
    ) -> None:
        self._devices = devices
        self._catalog = catalog
        self._target = target

    def status(
        self,
        *,
        bindings: Sequence[Mapping[str, Any]],
        profile_id: str,
        profile_revision: int,
        orientation: str,
    ) -> AutoconfigOutcome:
        """Estado observado. NÃO grava nada."""
        if not bindings:
            return AutoconfigOutcome(
                "not-configured", None, CatalogMatch(None, "no-device"), self._target
            )
        match = self._catalog.match(self._devices.identities())
        if match.autoconfig is None:
            return AutoconfigOutcome("awaiting-device", None, match, self._target)
        resolution = autoconfig_mod.resolve(bindings, match.autoconfig)
        if not resolution.writable:
            return AutoconfigOutcome(
                "awaiting-device",
                resolution,
                match,
                self._target,
                detail="o controle não declara nenhuma das entradas do perfil",
            )
        if not self._target.declared or self._target.path is None:
            return AutoconfigOutcome("awaiting-emulator", resolution, match, self._target)
        if self._target.directory is None or not self._target.directory.is_dir():
            # Diretório declarado que não existe NO HOST. O caso concreto medido
            # aqui não é "o RetroArch ainda não criou": o Flatpak 1.22.2 declara
            # `/app/share/libretro/autoconfig`, que é o mount somente-leitura do
            # sandbox e não existe fora dele. Abrir o RetroArch não resolve —
            # falta uma integração de lançamento que aponte o emulador para um
            # diretório gerenciado e gravável.
            return AutoconfigOutcome(
                "awaiting-emulator",
                resolution,
                match,
                self._target,
                detail=(
                    f"{self._target.directory}: o diretório que o RetroArch declara não existe "
                    "neste host (caminho interno do sandbox Flatpak); o perfil não tem onde valer"
                ),
            )

        probe = _probe_target(self._target.path)
        if probe.kind == "foreign":
            return AutoconfigOutcome(
                "conflict",
                resolution,
                match,
                self._target,
                detail=f"{self._target.path}: {probe.detail}",
            )

        # Perfil incompleto NÃO é gravado. O critério desta entrega é gerar o
        # autoconfig somente quando todos os dados necessários estiverem
        # resolvidos, e meio perfil em disco é pior que perfil nenhum: o
        # RetroArch aceitaria o arquivo, as ações faltantes ficariam sem
        # binding, e o usuário veria um controle que responde pela metade sem
        # nada dizer por quê. `partial` é diagnóstico — o que falta aparece na
        # tela com o motivo, e o emulador segue nos padrões dele.
        if resolution.state == "partial":
            return AutoconfigOutcome(
                "partial",
                resolution,
                match,
                self._target,
                detail="o perfil não é gravado enquanto houver ação sem índice físico",
            )

        expected = self._render(resolution, match, profile_id, profile_revision, orientation)
        if probe.kind == "absent" or probe.text != expected:
            return AutoconfigOutcome("pending-write", resolution, match, self._target)
        return AutoconfigOutcome("applied", resolution, match, self._target)

    def plan(
        self,
        *,
        bindings: Sequence[Mapping[str, Any]],
        profile_id: str,
        profile_revision: int,
        orientation: str,
    ) -> transaction.Plan:
        """Plano transacional REAL para materializar o autoconfig.

        A versão anterior gravava aqui, por fora do núcleo transacional, e um
        plano vazio servia só de portão de confirmação. Isso produzia quatro
        defeitos que este desenho elimina de uma vez:

        - o plano não ficava ligado a perfil, revisão, orientação nem destino,
          então dava para confirmar o perfil A, trocar de perfil e gravar o B;
        - a operação era commitada ANTES do efeito, então falha de escrita
          devolvia sucesso transacional;
        - não havia backup, logo o `rollback` oferecido no histórico não
          removia nem restaurava nada — rollback falso;
        - a recusa a sobrescrever arquivo alheio dependia de uma verificação
          feita antes da escrita, com janela entre as duas.

        Com o conteúdo dentro do plano, o núcleo cuida de tudo: a precondição
        grava o fingerprint do alvo e `apply` a revalida, então QUALQUER
        mudança no destino entre planejar e aplicar — inclusive um arquivo
        estrangeiro que apareça na janela — reprova como plano obsoleto em vez
        de ser sobrescrita. O backup torna o rollback verdadeiro.
        """
        observed = self.status(
            bindings=bindings,
            profile_id=profile_id,
            profile_revision=profile_revision,
            orientation=orientation,
        )
        if observed.state != "pending-write":
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail=f"perfil não está pronto para gravar: {observed.label}",
            )
        resolution = observed.resolution
        path = self._target.path
        if resolution is None or path is None:  # pragma: no cover - implicado por pending-write
            raise SteamZeroError("E-TX-STALE-PLAN", detail="destino do autoconfig indefinido")
        content = self._render(
            resolution, observed.match, profile_id, profile_revision, orientation
        ).encode("utf-8")
        return transaction.plan_write_files(
            {path: content},
            root=path.parent,
            kind="controls.autoconfig.apply",
            skip_unchanged=True,
            # O destino é a configuração do RetroArch. Só planos assim poupam o
            # diretório preexistente do `chmod`; na árvore do SteamZero o modo
            # seguro continua sendo normalizado, como sempre foi.
            foreign_dir=True,
        )

    def apply(self, plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        """Aplica o plano pelo núcleo transacional, com backup e rollback."""
        plan = transaction.load_plan(plan_id)
        if plan.kind != "controls.autoconfig.apply":
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="plano não pertence ao autoconfig de controles"
            )
        return transaction.apply(plan_id, confirm_token)

    def _render(
        self,
        resolution: Resolution,
        match: CatalogMatch,
        profile_id: str,
        profile_revision: int,
        orientation: str,
    ) -> str:
        if match.autoconfig is None or match.device is None:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="dispositivo não resolvido")
        return autoconfig_mod.render_managed(
            resolution,
            identity=match.device,
            source=match.autoconfig,
            profile_id=profile_id,
            profile_revision=profile_revision,
            orientation=orientation,
        )
