# SPDX-License-Identifier: GPL-3.0-or-later
"""Cliente pequeno e fail-closed para o socket local do ``steamzero-core``."""

from __future__ import annotations

import base64
import gzip
import json
import os
import socket
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from typing import IO, Any

from steamzero.api import contracts
from steamzero.api.events import parse_event_cursor
from steamzero.service.socket_path import safe_socket_path

_MAX_RESPONSE = 1 << 20
#: Teto lógico pós-descompressão: o frame na rede continua limitado a
#: ``_MAX_RESPONSE``; isto impede que um payload descomprimido desborde a
#: memória do cliente (defesa contra resposta truncada ou maliciosa).
_MAX_DECODED = 16 << 20
_PAYLOAD_ENCODING = "gzip+base64"


class CoreUnavailable(ConnectionError):
    """Daemon ausente ou transporte local indisponível."""


class CoreProtocolError(RuntimeError):
    """Resposta do daemon não respeita o contrato JSON-RPC."""


class CoreAmbiguousResult(CoreProtocolError):
    """Round-trip interrompido ou resposta sem resultado determinístico.

    O daemon pode ter executado a chamada ou não. Para leitura o chamador
    pode degradar para o caminho local (código desta mesma geração); mutação
    nunca é repetida localmente.
    """


class CoreResponseTooLarge(CoreProtocolError):
    """A resposta do daemon passou do limite que o transporte aceita.

    Não é incompatibilidade de contrato: cliente e servidor concordam sobre o
    formato, e a carga é que não cabe. A distinção existe porque colapsar isto
    em ``E-API-CONTRACT`` mandava o usuário "atualizar o cliente ou o servidor"
    para um problema que atualização nenhuma resolve.

    Observado em 2026-08-27: `emulation workspace` num acervo real produz
    1.513.479 bytes contra o limite de 1 MiB, e o comando ficou inutilizável no
    host anunciando divergência de versão.
    """


class CoreSecurityRefusal(CoreProtocolError):
    """Socket local com ownership ou permissões inseguras.

    Não é ausência de daemon: é condição de segurança. Nunca degrada — a
    chamada falha com a causa declarada.
    """


class CoreGenerationMismatch(RuntimeError):
    """O daemon em execução pertence a outra geração da release.

    Foi exatamente este estado que produziu a regressão da a37: ``current``
    apontava para a a37 enquanto ``steamzero-core.service`` seguia executando o
    Python da a35. Nada falhava — a UI apenas recebia snapshots antigos, e o
    sintoma apareceu como "ícones sumiram" e "keys apagadas".

    Preferimos recusar barulhento a responder mentindo.
    """

    def __init__(self, client: dict[str, Any], daemon: dict[str, Any]) -> None:
        self.client = client
        self.daemon = daemon
        super().__init__(
            "daemon de outra geração: cliente "
            f"{client.get('releaseId') or client.get('packageVersion')} "
            f"contra daemon {daemon.get('releaseId') or daemon.get('packageVersion')}"
        )


@dataclass(frozen=True)
class Invocation:
    envelope: dict[str, Any]
    exit_code: int


def daemon_identity(*, timeout: float = 2.0) -> dict[str, Any]:
    """Identidade declarada pelo daemon em execução, via ``system.hello``."""
    result = _call(1, "system.hello", {}, timeout=timeout)
    identity = result.get("identity")
    if isinstance(identity, dict):
        return identity
    # Daemon anterior à publicação de identidade: o que ele sabe dizer é a
    # versão. Melhor um dado parcial declarado que assumir compatibilidade.
    return {
        "packageVersion": str(result.get("daemonVersion") or ""),
        "sourceCommit": "",
        "releaseId": "",
    }


def daemon_pid(*, timeout: float = 2.0) -> int | None:
    """PID do daemon via ``system.hello``; None se indisponível ou ambíguo.

    É a identidade efêmera usada pelo probe de recursos (GAP-G30) para
    atribuir o consumo do daemon sem tocar em units nem command lines.
    """
    try:
        result = _call(1, "system.hello", {}, timeout=timeout)
    except (CoreProtocolError, CoreUnavailable, OSError):
        return None
    pid = result.get("pid")
    return pid if isinstance(pid, int) and pid > 1 else None


def verify_generation(*, timeout: float = 2.0) -> dict[str, Any]:
    """Confronta a identidade do processo local com a do daemon.

    Levanta ``CoreGenerationMismatch`` quando divergem. Identidade desconhecida
    de qualquer lado também recusa: não sabemos o que estamos comparando, e
    assumir compatibilidade sem prova é o erro que se quer evitar.
    """
    from steamzero.core.identity import UNKNOWN_COMMIT, runtime_identity

    mine = runtime_identity()
    theirs = daemon_identity(timeout=timeout)
    their_commit = str(theirs.get("sourceCommit") or "")
    their_known = bool(their_commit) and their_commit != UNKNOWN_COMMIT

    if mine.known and their_known:
        # Caminho verificado: os dois lados sabem sua origem e ela precisa bater.
        if mine.source_commit == their_commit and mine.release_id == theirs.get("releaseId"):
            return theirs
        raise CoreGenerationMismatch(mine.to_dict(), theirs)

    if not mine.known and not their_known:
        # Nenhum dos lados carrega proveniência: árvore de desenvolvimento ou
        # instalação cujo hook de build não rodou. Não há release para proteger
        # nem evidência de divergência, e recusar tornaria o daemon inutilizável
        # em desenvolvimento. Exigir proveniência é papel do preflight de
        # promoção, que reprova identidade ausente antes de instalar.
        if mine.package_version == str(theirs.get("packageVersion") or ""):
            return theirs
        raise CoreGenerationMismatch(mine.to_dict(), theirs)

    # Um lado sabe e o outro não: é justamente a assimetria da a37, em que a
    # release nova conhecia sua origem e o processo sobrevivente não.
    raise CoreGenerationMismatch(mine.to_dict(), theirs)


def _unwrap_result(result: dict[str, Any]) -> dict[str, Any]:
    """Desembrulha resultado comprimido; sem o marcador, devolve como veio."""
    if result.get("__payload") != _PAYLOAD_ENCODING:
        return result
    data = result.get("data")
    decoded_size = result.get("decodedSize")
    if not isinstance(data, str) or not isinstance(decoded_size, int):
        raise CoreProtocolError("resultado comprimido malformado")
    try:
        raw = gzip.decompress(base64.b64decode(data, validate=True))
    except (ValueError, OSError) as exc:
        raise CoreProtocolError(f"resultado comprimido ilegível: {exc}") from exc
    if len(raw) != decoded_size:
        raise CoreProtocolError(
            f"tamanho declarado {decoded_size} difere do descomprimido {len(raw)}"
        )
    if len(raw) > _MAX_DECODED:
        raise CoreResponseTooLarge(
            f"resposta descomprimida de {len(raw)} bytes excede o limite de {_MAX_DECODED}"
        )
    try:
        decoded: dict[str, Any] = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreProtocolError("resultado descomprimido não é JSON") from exc
    # O payload comprimido é a RESPOSTA inteira; o chamador quer o result dela.
    inner = decoded.get("result")
    if not isinstance(inner, dict):
        raise CoreProtocolError("resultado descomprimido não carrega um result")
    return inner


def _call(
    request_id: int, method: str, params: dict[str, Any], *, timeout: float
) -> dict[str, Any]:
    """Um round-trip JSON-RPC, com o envelope já validado.

    Anuncia ``acceptGzip``: respostas grandes chegam comprimidas e são
    desembrulhadas aqui, transparente para o chamador. Servidor antigo ignora
    o campo e responde sem comprimir.
    """
    request = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
                "acceptGzip": True,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    client = _connect(timeout)
    try:
        client.sendall(request)
        payload = _read_line(client)
    except OSError as exc:
        raise CoreAmbiguousResult("resultado da chamada é ambíguo") from exc
    finally:
        client.close()
    try:
        response = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreProtocolError("resposta JSON inválida") from exc
    if (
        not isinstance(response, dict)
        or response.get("jsonrpc") != "2.0"
        or response.get("id") != request_id
    ):
        raise CoreProtocolError("envelope JSON-RPC inválido")
    error = response.get("error")
    if error is not None:
        raise CoreProtocolError(f"daemon recusou a chamada: {error}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise CoreAmbiguousResult("resultado ausente")
    return _unwrap_result(result)


def invoke(method: str, params: dict[str, str], *, timeout: float = 2.0) -> Invocation:
    result = _call(1, method, dict(params), timeout=timeout)
    envelope = result.get("envelope")
    exit_code = result.get("exitCode")
    if not isinstance(envelope, dict) or not isinstance(exit_code, int):
        raise CoreAmbiguousResult("resultado tipado inválido")
    return Invocation(envelope=envelope, exit_code=exit_code)


def subscribe_events(
    params: dict[str, Any],
    *,
    connect_timeout: float = 2.0,
    reconnect_attempts: int = 3,
) -> Iterator[dict[str, Any]]:
    """Segue notificações event-v1 e retoma pelo último cursor confirmado."""
    if reconnect_attempts < 0:
        raise ValueError("reconnect_attempts não pode ser negativo")
    request_id = 1
    current_params = dict(params)
    cursor_value = current_params.get("cursor")
    if cursor_value is not None:
        if not isinstance(cursor_value, str):
            raise CoreProtocolError("cursor da assinatura precisa ser texto")
        try:
            parse_event_cursor(cursor_value)
        except ValueError as exc:
            raise CoreProtocolError(str(exc)) from exc
    current_cursor = cursor_value
    connected = False
    failures = 0
    while True:
        try:
            client = _connect(connect_timeout)
        except CoreUnavailable as exc:
            if not connected:
                raise
            failures += 1
            if failures > reconnect_attempts:
                raise CoreProtocolError("assinatura perdeu o daemon") from exc
            continue
        connected = True
        if current_cursor is not None:
            current_params["cursor"] = current_cursor
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "events.subscribe",
            "params": current_params,
        }
        reader = client.makefile("rb")
        try:
            client.sendall(
                json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                + b"\n"
            )
            acknowledgement = _read_json_line(reader)
            subscription_id, acknowledged_cursor = _subscription_ack(acknowledgement, request_id)
            if current_cursor is not None and acknowledged_cursor != current_cursor:
                raise CoreProtocolError("ack da assinatura alterou o cursor solicitado")
            current_cursor = acknowledged_cursor
            client.settimeout(None)
            while True:
                message = _read_json_line(reader, disconnected=True)
                method = message.get("method")
                notification_params = message.get("params")
                if (
                    message.get("jsonrpc") != "2.0"
                    or not isinstance(notification_params, dict)
                    or notification_params.get("subscriptionId") != subscription_id
                ):
                    raise CoreProtocolError("notificação da assinatura inválida")
                notification_cursor = notification_params.get("cursor")
                if not isinstance(notification_cursor, str):
                    raise CoreProtocolError("cursor da notificação inválido")
                try:
                    parsed_cursor = parse_event_cursor(notification_cursor)
                    previous_cursor = parse_event_cursor(current_cursor)
                except ValueError as exc:
                    raise CoreProtocolError(str(exc)) from exc
                if method == "events.complete":
                    if parsed_cursor != previous_cursor:
                        raise CoreProtocolError("cursor final divergiu do último evento")
                    return
                if method != "events.event":
                    raise CoreProtocolError("método de notificação desconhecido")
                event = notification_params.get("event")
                if (
                    not isinstance(event, dict)
                    or event.get("seq") != parsed_cursor
                    or parsed_cursor <= previous_cursor
                ):
                    raise CoreProtocolError("evento fora de ordem ou duplicado")
                try:
                    contracts.validate(event, "event-v1.schema.json")
                except Exception as exc:
                    raise CoreProtocolError("evento não respeita event-v1") from exc
                current_cursor = notification_cursor
                yield event
        except _StreamDisconnected as exc:
            failures += 1
            if failures > reconnect_attempts:
                raise CoreProtocolError("assinatura interrompida após reconexões") from exc
        except OSError as exc:
            failures += 1
            if failures > reconnect_attempts:
                raise CoreProtocolError("assinatura interrompida após reconexões") from exc
        finally:
            reader.close()
            client.close()


class _StreamDisconnected(ConnectionError):
    pass


def _connect(timeout: float) -> socket.socket:
    try:
        path = safe_socket_path()
    except PermissionError as exc:
        raise CoreSecurityRefusal("socket local possui ownership ou permissões inseguras") from exc
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise CoreUnavailable(str(exc)) from exc
    if (
        path.is_symlink()
        or not stat.S_ISSOCK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_mode & 0o077
    ):
        raise CoreSecurityRefusal("socket local possui ownership ou permissões inseguras")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(path))
    except OSError as exc:
        client.close()
        raise CoreUnavailable(str(exc)) from exc
    return client


def _read_json_line(reader: IO[bytes], *, disconnected: bool = False) -> dict[str, Any]:
    payload = reader.readline(_MAX_RESPONSE + 1)
    if not payload:
        if disconnected:
            raise _StreamDisconnected("conexão encerrada")
        raise CoreProtocolError("resposta incompleta")
    if len(payload) > _MAX_RESPONSE:
        raise CoreResponseTooLarge(
            f"resposta de {len(payload)} bytes excede o limite de {_MAX_RESPONSE}"
        )
    if not payload.endswith(b"\n"):
        raise CoreProtocolError("resposta incompleta")
    try:
        response = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreProtocolError("resposta JSON inválida") from exc
    if not isinstance(response, dict):
        raise CoreProtocolError("mensagem JSON-RPC precisa ser objeto")
    return response


def _subscription_ack(response: dict[str, Any], request_id: str | int) -> tuple[str, str]:
    if response.get("jsonrpc") != "2.0" or response.get("id") != request_id:
        raise CoreProtocolError("ack da assinatura inválido")
    error = response.get("error")
    if error is not None:
        raise CoreProtocolError(f"daemon recusou a assinatura: {error}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise CoreProtocolError("ack da assinatura ausente")
    subscription_id = result.get("subscriptionId")
    cursor = result.get("cursor")
    if (
        not isinstance(subscription_id, str)
        or not subscription_id
        or not isinstance(cursor, str)
        or result.get("transport") != "json-rpc-notifications"
    ):
        raise CoreProtocolError("ack da assinatura tipado inválido")
    try:
        parse_event_cursor(cursor)
    except ValueError as exc:
        raise CoreProtocolError(str(exc)) from exc
    return subscription_id, cursor


def _read_line(client: socket.socket) -> str:
    data = bytearray()
    while len(data) <= _MAX_RESPONSE:
        chunk = client.recv(min(65536, _MAX_RESPONSE + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in chunk:
            break
    if len(data) > _MAX_RESPONSE:
        raise CoreResponseTooLarge(
            f"resposta de {len(data)} bytes excede o limite de {_MAX_RESPONSE}"
        )
    line, separator, _rest = bytes(data).partition(b"\n")
    if not separator:
        raise CoreProtocolError("resposta incompleta")
    return line.decode("utf-8")
