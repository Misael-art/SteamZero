# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Edição transacional e byte-preserving de Launch Options da Steam.

O adapter nunca reserializa o ``localconfig.vdf`` inteiro. Um parser estrutural
localiza apenas ``apps/<appid>/LaunchOptions`` e o patch troca ou insere essa
folha, preservando todos os demais bytes. Mutação exige Steam encerrada.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NoReturn

from steamzero.core import fs, transaction
from steamzero.core.errors import SteamZeroError

RunningProbe = Callable[[], bool]

_MAX_VDF_BYTES = 16 * 1024 * 1024
_STEAMID64_BASE = 76561197960265728
_LOCALCONFIG_PATH = ("UserLocalConfigStore", "Software", "Valve", "Steam", "apps")


def _default_roots() -> tuple[Path, ...]:
    home = Path.home()
    return (
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    )


def _steam_running(proc_root: Path | None = None) -> bool:
    """``proc_root`` injetável: sem ele o ramo positivo só executa em máquina com
    Steam aberto, e a cobertura passa a depender do que está rodando."""
    try:
        entries = (proc_root if proc_root is not None else Path("/proc")).iterdir()
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            name = (entry / "comm").read_text(encoding="utf-8").strip().casefold()
        except OSError:
            continue
        if name in {"steam", "steamwebhelper"}:
            return True
    return False


@dataclass(frozen=True)
class _Token:
    kind: Literal["string", "open", "close"]
    start: int
    end: int
    value: str = ""


@dataclass(frozen=True)
class _Entry:
    key: str
    key_token: _Token
    value_token: _Token | None = None
    block: _Block | None = None


@dataclass(frozen=True)
class _Block:
    entries: tuple[_Entry, ...]
    close_start: int | None

    def blocks(self, key: str) -> tuple[_Block, ...]:
        folded = key.casefold()
        return tuple(
            entry.block
            for entry in self.entries
            if entry.key.casefold() == folded and entry.block is not None
        )

    def leaves(self, key: str) -> tuple[_Token, ...]:
        folded = key.casefold()
        return tuple(
            entry.value_token
            for entry in self.entries
            if entry.key.casefold() == folded and entry.value_token is not None
        )

    def matching(self, key: str) -> tuple[_Entry, ...]:
        folded = key.casefold()
        return tuple(entry for entry in self.entries if entry.key.casefold() == folded)


class _VdfDocument:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self._tokens = self._tokenize(data)
        self._position = 0
        self.root = self._parse_block(expect_close=False)
        if self._position != len(self._tokens):
            self._invalid("tokens após o documento")

    @staticmethod
    def _invalid(detail: str) -> NoReturn:
        raise SteamZeroError("E-STATE-INTEGRITY", detail=f"VDF Steam inválido: {detail}")

    @classmethod
    def _tokenize(cls, data: bytes) -> tuple[_Token, ...]:
        tokens: list[_Token] = []
        index = 0
        while index < len(data):
            value = data[index]
            if value in b" \t\r\n":
                index += 1
                continue
            if data[index : index + 2] == b"//":
                newline = data.find(b"\n", index + 2)
                index = len(data) if newline < 0 else newline + 1
                continue
            if value == ord("{"):
                tokens.append(_Token("open", index, index + 1))
                index += 1
                continue
            if value == ord("}"):
                tokens.append(_Token("close", index, index + 1))
                index += 1
                continue
            if value != ord('"'):
                cls._invalid(f"token não citado no byte {index}")
            start = index
            index += 1
            decoded = bytearray()
            while index < len(data):
                current = data[index]
                if current == ord('"'):
                    index += 1
                    break
                if current == ord("\\"):
                    index += 1
                    if index >= len(data):
                        cls._invalid("escape incompleto")
                    escaped = data[index]
                    decoded.extend(
                        {ord('"'): b'"', ord("\\"): b"\\"}.get(escaped, bytes((escaped,)))
                    )
                    index += 1
                    continue
                if current == 0:
                    cls._invalid("NUL em string")
                decoded.append(current)
                index += 1
            else:
                cls._invalid("string sem fechamento")
            tokens.append(
                _Token("string", start, index, decoded.decode("utf-8", errors="surrogateescape"))
            )
        return tuple(tokens)

    def _parse_block(self, *, expect_close: bool) -> _Block:
        entries: list[_Entry] = []
        while self._position < len(self._tokens):
            token = self._tokens[self._position]
            if token.kind == "close":
                if not expect_close:
                    self._invalid("chave de fechamento inesperada")
                self._position += 1
                return _Block(tuple(entries), token.start)
            if token.kind != "string":
                self._invalid("chave textual esperada")
            key = token
            self._position += 1
            if self._position >= len(self._tokens):
                self._invalid(f"valor ausente para {key.value}")
            value = self._tokens[self._position]
            self._position += 1
            if value.kind == "string":
                entries.append(_Entry(key.value, key, value_token=value))
                continue
            if value.kind != "open":
                self._invalid(f"bloco ou valor esperado para {key.value}")
            entries.append(_Entry(key.value, key, block=self._parse_block(expect_close=True)))
        if expect_close:
            self._invalid("bloco sem fechamento")
        return _Block(tuple(entries), None)

    def unique_block(self, parent: _Block, key: str) -> _Block:
        found = parent.matching(key)
        if len(found) != 1:
            self._invalid(f"bloco {key} ausente ou duplicado")
        block = found[0].block
        if block is None:
            self._invalid(f"bloco {key} ausente ou duplicado")
        return block

    def path(self, keys: Sequence[str]) -> _Block:
        current = self.root
        for key in keys:
            current = self.unique_block(current, key)
        return current


def _quote(value: str) -> bytes:
    if "\x00" in value or "\n" in value or "\r" in value:
        raise SteamZeroError("E-API-SCHEMA", detail="Launch Options contém controle inválido")
    return b'"' + value.replace("\\", "\\\\").replace('"', '\\"').encode() + b'"'


def _line_start(data: bytes, offset: int) -> int:
    newline = data.rfind(b"\n", 0, offset)
    return 0 if newline < 0 else newline + 1


def _indent_at(data: bytes, offset: int) -> tuple[int, bytes]:
    start = _line_start(data, offset)
    indent = data[start:offset]
    if any(value not in b" \t\r" for value in indent):
        raise SteamZeroError("E-STATE-INTEGRITY", detail="VDF Steam sem indentação segura")
    return start, indent.removesuffix(b"\r")


def _newline(data: bytes) -> bytes:
    return b"\r\n" if b"\r\n" in data else b"\n"


@dataclass(frozen=True)
class LaunchOptionsPatch:
    content: bytes
    previous_state: str
    previous_present: bool


def patch_launch_options(data: bytes, app_id: str, desired: str) -> LaunchOptionsPatch:
    if not app_id.isdigit() or len(app_id) > 32:
        raise SteamZeroError("E-API-SCHEMA", detail="gameId inválido")
    if len(data) > _MAX_VDF_BYTES:
        raise SteamZeroError("E-STATE-INTEGRITY", detail="localconfig.vdf excede 16 MiB")
    document = _VdfDocument(data)
    apps = document.path(_LOCALCONFIG_PATH)
    app_entries = apps.matching(app_id)
    if len(app_entries) > 1 or (app_entries and app_entries[0].block is None):
        raise SteamZeroError("E-STATE-INTEGRITY", detail="AppID duplicado no localconfig.vdf")
    desired_token = _quote(desired)
    newline = _newline(data)

    if app_entries:
        app = app_entries[0].block
        if app is None:  # defesa adicional para narrowing e documentos corrompidos
            raise SteamZeroError("E-STATE-INTEGRITY", detail="AppID sem bloco")
        launch_entries = app.matching("LaunchOptions")
        if len(launch_entries) > 1 or (launch_entries and launch_entries[0].value_token is None):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="LaunchOptions duplicada")
        if launch_entries:
            token = launch_entries[0].value_token
            if token is None:  # defesa adicional para narrowing e documentos corrompidos
                raise SteamZeroError("E-STATE-INTEGRITY", detail="LaunchOptions sem valor")
            previous = token.value
            return LaunchOptionsPatch(
                data[: token.start] + desired_token + data[token.end :],
                "managed" if previous == desired else "foreign",
                True,
            )
        if app.close_start is None:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="bloco do AppID sem fechamento")
        line_start, close_indent = _indent_at(data, app.close_start)
        child_indent = close_indent + b"\t"
        inserted = child_indent + b'"LaunchOptions"\t\t' + desired_token + newline
        return LaunchOptionsPatch(
            data[:line_start] + inserted + data[line_start:], "missing", False
        )

    if apps.close_start is None:
        raise SteamZeroError("E-STATE-INTEGRITY", detail="bloco apps sem fechamento")
    line_start, close_indent = _indent_at(data, apps.close_start)
    app_indent = close_indent + b"\t"
    leaf_indent = app_indent + b"\t"
    inserted = (
        app_indent
        + _quote(app_id)
        + newline
        + app_indent
        + b"{"
        + newline
        + leaf_indent
        + b'"LaunchOptions"\t\t'
        + desired_token
        + newline
        + app_indent
        + b"}"
        + newline
    )
    return LaunchOptionsPatch(data[:line_start] + inserted + data[line_start:], "missing", False)


class SteamLaunchOptionsManager:
    """Planeja e aplica uma única folha VDF com rollback byte-idêntico."""

    def __init__(
        self,
        *,
        roots: Sequence[Path] | None = None,
        running_probe: RunningProbe = _steam_running,
    ) -> None:
        self._roots = tuple(roots) if roots is not None else _default_roots()
        self._running_probe = running_probe
        self._last_operation_id: str | None = None

    @staticmethod
    def desired(app_id: str) -> str:
        if not app_id.isdigit() or len(app_id) > 32:
            raise SteamZeroError("E-API-SCHEMA", detail="gameId inválido")
        return f"steamzero-launch --appid {app_id} -- %command%"

    def status(self, app_id: str) -> dict[str, Any]:
        desired = self.desired(app_id)
        try:
            target = self._active_localconfig()
            data = self._read_target(target)
            patched = patch_launch_options(data, app_id, desired)
        except SteamZeroError as exc:
            return {
                "state": "unavailable",
                "statusLabel": "Configuração Steam indisponível",
                "detail": exc.detail,
                "steamRunning": self._running_probe(),
                "managed": False,
                "lastOperationId": self._last_operation_id,
            }
        running = self._running_probe()
        state = (
            "managed"
            if patched.previous_state == "managed"
            else "steam-running"
            if running
            else patched.previous_state
        )
        labels = {
            "managed": "Configurado automaticamente",
            "steam-running": "Feche a Steam para configurar",
            "foreign": "Launch Options existente",
            "missing": "Configuração automática disponível",
        }
        return {
            "state": state,
            "statusLabel": labels[state],
            "detail": (
                "O wrapper SteamZero já é a Launch Option deste jogo."
                if state == "managed"
                else "A configuração existente será preservada pelo rollback G-FULL."
                if patched.previous_present
                else "O SteamZero pode registrar o wrapper sem alterar outros jogos."
            ),
            "steamRunning": running,
            "managed": state == "managed",
            "replacesExisting": patched.previous_present and state != "managed",
            "lastOperationId": self._last_operation_id,
        }

    def plan(self, app_id: str) -> dict[str, Any]:
        if self._running_probe():
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail="feche completamente a Steam antes de configurar"
            )
        target = self._active_localconfig()
        original = self._read_target(target)
        desired = self.desired(app_id)
        patched = patch_launch_options(original, app_id, desired)
        plan = transaction.plan_write_files(
            {target: patched.content},
            root=target.parents[1],
            kind=f"steam.launch-options.configure:{app_id}",
        )
        if (
            len(plan.preconditions) != 1
            or plan.preconditions[0].target != str(target)
            or plan.preconditions[0].fingerprint != fs.hash_bytes(original)
        ):
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="a configuração Steam mudou durante o planejamento"
            )
        verb = "Substituir" if patched.previous_present else "Adicionar"
        return {
            "planId": plan.plan_id,
            "confirmToken": plan.confirm_token,
            "expiresAt": plan.expires_at,
            "gameId": app_id,
            "changes": [f"{verb} Launch Options somente para o jogo selecionado"],
            "replacesExisting": patched.previous_present,
            "rollbackGuarantee": plan.rollback_guarantee,
        }

    def apply(self, plan_id: str, confirm_token: str, app_id: str) -> dict[str, Any]:
        if self._running_probe():
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail="a Steam foi aberta; feche-a e revise novamente"
            )
        target = self._active_localconfig()
        plan = transaction.load_plan(plan_id)
        current = self._read_target(target)
        expected = patch_launch_options(current, app_id, self.desired(app_id)).content
        if (
            plan.kind != f"steam.launch-options.configure:{app_id}"
            or Path(plan.root) != target.parents[1]
            or len(plan.actions) != 1
            or plan.actions[0].kind != "write"
            or plan.actions[0].source is not None
            or plan.actions[0].target != str(target)
            or plan.actions[0].new_content() != expected
            or len(plan.preconditions) != 1
            or plan.preconditions[0].target != str(target)
        ):
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não pertence às Launch Options")
        desired = self.desired(app_id)

        def verify() -> None:
            patched = patch_launch_options(self._read_target(target), app_id, desired)
            if patched.previous_state != "managed":
                raise RuntimeError("Launch Options não foi observada após apply")

        result = transaction.apply(plan_id, confirm_token, smoke=verify)
        self._last_operation_id = result.operation_id
        return {
            "status": "configured",
            "gameId": app_id,
            "operationId": result.operation_id,
            "message": "Lançamento gerenciado configurado; a Steam já pode ser aberta.",
        }

    def rollback(self, operation_id: str) -> dict[str, Any]:
        if self._running_probe():
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="feche a Steam antes de desfazer")
        if operation_id != self._last_operation_id:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="operação não pertence a esta sessão")
        result = transaction.rollback(operation_id, reason="steam-launch-options-manual")
        self._last_operation_id = None
        return {
            "status": result.status,
            "operationId": operation_id,
            "message": "Launch Options anterior restaurada byte a byte.",
        }

    def _active_localconfig(self) -> Path:
        candidates: dict[str, list[Path]] = {}
        for root in self._roots:
            userdata = root / "userdata"
            try:
                accounts = tuple(userdata.iterdir())
            except OSError:
                continue
            for account in accounts:
                config = account / "config"
                target = config / "localconfig.vdf"
                if (
                    account.name.isdigit()
                    and account.is_dir()
                    and not account.is_symlink()
                    and config.is_dir()
                    and not config.is_symlink()
                    and target.is_file()
                    and not target.is_symlink()
                ):
                    resolved_account = account.resolve()
                    resolved_target = target.resolve()
                    if not resolved_target.is_relative_to(resolved_account):
                        continue
                    targets = candidates.setdefault(account.name, [])
                    if resolved_target not in targets:
                        targets.append(resolved_target)
        if not candidates:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="localconfig.vdf não encontrado")
        flattened = [target for targets in candidates.values() for target in targets]
        if len(flattened) == 1:
            return flattened[0]
        active = self._active_account_id()
        if active is not None and len(candidates.get(active, [])) == 1:
            return candidates[active][0]
        raise SteamZeroError(
            "E-COMPONENT-DEGRADED",
            detail="há múltiplas contas Steam e nenhuma conta ativa pôde ser determinada",
        )

    def _active_account_id(self) -> str | None:
        matched: set[str] = set()
        for root in self._roots:
            path = root / "config/loginusers.vdf"
            try:
                data = self._read_target(path)
                users = _VdfDocument(data).path(("users",))
            except SteamZeroError:
                continue
            for entry in users.entries:
                if entry.block is None or not entry.key.isdigit():
                    continue
                recent = entry.block.leaves("MostRecent")
                if len(recent) == 1 and recent[0].value == "1":
                    steam_id = int(entry.key)
                    if steam_id >= _STEAMID64_BASE:
                        matched.add(str(steam_id - _STEAMID64_BASE))
        return next(iter(matched)) if len(matched) == 1 else None

    @staticmethod
    def _read_target(path: Path) -> bytes:
        try:
            size = path.stat().st_size
            if size > _MAX_VDF_BYTES or path.is_symlink():
                raise SteamZeroError(
                    "E-STATE-INTEGRITY", detail="arquivo Steam excede limite ou é symlink"
                )
            return path.read_bytes()
        except SteamZeroError:
            raise
        except OSError as exc:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail="não foi possível ler configuração Steam"
            ) from exc
