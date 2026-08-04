# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Quarentena, restauração e expurgo de artefatos órfãos do state home (A42).

A v1 (G25) provou o conceito: plano com token, apply que move para quarentena,
nunca deleta. Ela não era segura o bastante para rodar contra o acervo real de
~1,1 GB do host, por quatro motivos:

1. o plano guardava caminhos ABSOLUTOS e o apply os usava sem validar — um
   plano adulterado moveria qualquer coisa do disco;
2. não havia digest: entre plano e apply a árvore podia mudar e ninguém saberia;
3. a quarentena era ``quarantine/<kind>/<name>``, compartilhada entre execuções —
   duas limpezas colidiam no mesmo destino;
4. falha no meio deixava metade movida, sem inventário e sem volta.

Aqui o inventário é RELATIVO ao state home e revalidado na aplicação; a
quarentena é isolada por operação; a falha parcial restaura o que já moveu; e o
expurgo é irreversível, em duas fases, recusado antes da retenção — sem flag de
bypass, porque bypass de retenção é a forma como se apaga o que ainda importava.

Nenhum código de erro novo é introduzido: todos os usados aqui já constam do
catálogo autoritativo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, lock, paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain import state_audit

#: Versão do payload de cleanup. O envelope público segue 2.0; isto versiona só
#: o corpo, que ganhou digest, bytes, expiração e inventário relativo.
SCHEMA_VERSION = 2

#: Um plano revisado envelhece: o estado que ele descreve pode ter mudado.
PLAN_TTL_SECONDS = 3600

#: Retenção da quarentena antes de o expurgo ser permitido.
RETENTION_DAYS = 7

_LOCK_RESOURCE = "state-cleanup"
_QUARANTINE_SUBDIR = "state-cleanup"
_HISTORY_SUBDIR = "cleanup-history"
_MANIFEST_NAME = "manifest.json"
_PRIVATE_FILE = 0o600

_KIND_ROOTS = {
    "staging": paths.staging_dir,
    "backup": paths.backups_dir,
    "journal": paths.journal_dir,
}


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _parse_iso(text: str, *, field: str) -> datetime:
    try:
        return datetime.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise SteamZeroError(
            "E-STATE-INTEGRITY", detail=f"campo {field} não é um instante válido"
        ) from exc


def quarantine_root() -> Path:
    return paths.quarantine_dir() / _QUARANTINE_SUBDIR


def quarantine_for_cleanup(cleanup_id: str) -> Path:
    """Diretório isolado desta operação. ULID validado como nome relativo."""
    fs.validate_relative_entry(cleanup_id)
    return fs.resolve_within(quarantine_root(), quarantine_root() / cleanup_id)


def history_path(cleanup_id: str) -> Path:
    fs.validate_relative_entry(cleanup_id)
    root = paths.state_home() / _HISTORY_SUBDIR
    return fs.resolve_within(root, root / f"{cleanup_id}.json")


# ---------------------------------------------------------------------------
# Digest determinístico
# ---------------------------------------------------------------------------


def _reject_unsafe(path: Path) -> None:
    """Recusa symlink e arquivo especial — só diretório ou arquivo regular.

    Symlink em quarentena é como se apaga o alvo sem querer: mover o link é
    inofensivo, mas restaurá-lo por cima de outro caminho não é, e um link para
    fora do state home tornaria o inventário mentiroso.
    """
    if path.is_symlink():
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail=f"symlink recusado: {path.name}")
    if not (path.is_dir() or path.is_file()):
        raise SteamZeroError(
            "E-CONTENT-UNSAFE-PATH", detail=f"entrada não é arquivo nem diretório: {path.name}"
        )


def measure(path: Path) -> tuple[int, str]:
    """Bytes lógicos e digest SHA-256 determinístico de um arquivo ou árvore.

    Para árvore, o digest cobre caminho relativo, tamanho e conteúdo de cada
    arquivo, em ordem estável — dois diretórios idênticos dão o mesmo valor em
    qualquer máquina, e qualquer mudança dentro muda o resultado.
    """
    _reject_unsafe(path)
    if path.is_file():
        return path.stat().st_size, fs.hash_file(path, algo="sha256")

    total = 0
    lines: list[str] = []
    for child in sorted(fs.iter_files(path), key=lambda item: str(item)):
        _reject_unsafe(child)
        rel = child.relative_to(path).as_posix()
        size = child.stat().st_size
        total += size
        lines.append(f"{rel}\0{size}\0{fs.hash_file(child, algo='sha256')}")
    digest = fs.hash_bytes("\n".join(lines).encode("utf-8"), algo="sha256")
    return total, digest


# ---------------------------------------------------------------------------
# Fase 1 — plano
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CleanupItem:
    """Artefato órfão candidato à quarentena, endereçado relativo ao state home."""

    kind: str
    name: str
    relpath: str
    size_bytes: int
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "relpath": self.relpath,
            "bytes": self.size_bytes,
            "digest": self.digest,
        }


def _source_for(kind: str, name: str) -> Path:
    """Caminho absoluto do artefato, com traversal barrado pela raiz do kind."""
    root_factory = _KIND_ROOTS.get(kind)
    if root_factory is None:
        raise SteamZeroError("E-API-SCHEMA", detail=f"tipo de artefato desconhecido: {kind!r}")
    fs.validate_relative_entry(name)
    root = root_factory()
    return fs.resolve_within(root, root / name)


def _relpath(path: Path) -> str:
    home = paths.state_home().resolve()
    return path.resolve().relative_to(home).as_posix()


def plan(report: state_audit.AuditReport) -> dict[str, Any]:
    """Constrói o plano de quarentena a partir de uma auditoria.

    O plano é persistido com token e prazo. Ele descreve o que será movido, o
    quanto isso pesa e o digest de cada item — para que a aplicação possa
    recusar se algo mudou desde a revisão.
    """
    items: list[CleanupItem] = []
    for kind, names in (
        ("staging", report.orphan_staging),
        ("backup", report.orphan_backups),
        ("journal", report.orphan_journals),
    ):
        for name in names:
            source = _source_for(kind, name)
            if not source.exists():
                continue
            size, digest = measure(source)
            items.append(CleanupItem(kind, name, _relpath(source), size, digest))

    created = _now()
    payload: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "cleanup",
        "planId": ids.new_ulid(),
        "confirmToken": ids.new_ulid(),
        "createdAt": _iso(created),
        "expiresAt": _iso(created + timedelta(seconds=PLAN_TTL_SECONDS)),
        "count": len(items),
        "totalBytes": sum(item.size_bytes for item in items),
        "items": [item.to_dict() for item in items],
    }
    fs.ensure_dir(paths.plans_dir())
    fs.write_atomic_text(
        paths.plan_path(str(payload["planId"])),
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
    )
    return payload


def _load_plan(plan_id: str, confirm_token: str, *, kind: str) -> dict[str, Any]:
    fs.validate_relative_entry(plan_id)
    plan_file = paths.plan_path(plan_id)
    if not plan_file.is_file():
        raise SteamZeroError("E-TX-STALE-PLAN", detail=f"plano inexistente: {plan_id}")
    payload: dict[str, Any] = json.loads(plan_file.read_text(encoding="utf-8"))
    if int(payload.get("schemaVersion", 0)) != SCHEMA_VERSION:
        raise SteamZeroError(
            "E-TX-STALE-PLAN",
            detail=(
                f"plano em schemaVersion {payload.get('schemaVersion')}; esperado {SCHEMA_VERSION}"
            ),
        )
    # Um token de restauração não pode autorizar um expurgo: são operações com
    # reversibilidade oposta e o operador revisou uma, não a outra.
    if str(payload.get("kind")) != kind:
        raise SteamZeroError(
            "E-TX-STALE-PLAN",
            detail=f"plano é de {payload.get('kind')!r}, não de {kind!r}",
        )
    if payload.get("confirmToken") != confirm_token:
        raise SteamZeroError(
            "E-TX-CONFIRM-REQUIRED", detail="token de confirmação não corresponde ao plano"
        )
    if _now() >= _parse_iso(str(payload.get("expiresAt")), field="expiresAt"):
        raise SteamZeroError(
            "E-TX-STALE-PLAN",
            detail="plano expirado; gere um novo e revise antes de aplicar",
        )
    return payload


# ---------------------------------------------------------------------------
# Fase 2 — quarentena
# ---------------------------------------------------------------------------


def _current_orphans() -> dict[str, set[str]]:
    with StateStore() as store:
        store.migrate()
        report = state_audit.audit(store)
    return {
        "staging": set(report.orphan_staging),
        "backup": set(report.orphan_backups),
        "journal": set(report.orphan_journals),
    }


def _verify_item(item: dict[str, Any], orphans: dict[str, set[str]]) -> Path:
    """Reconfere um item do plano contra o estado vivo. Devolve a origem validada.

    O plano descreve o passado; a aplicação precisa do presente. Um item que
    deixou de ser órfão significa que uma operação voltou a referenciá-lo —
    movê-lo seria arrancar o chão de uma transação em curso.
    """
    kind = str(item["kind"])
    name = str(item["name"])
    source = _source_for(kind, name)

    if name not in orphans.get(kind, set()):
        raise SteamZeroError(
            "E-TX-STALE-PLAN",
            detail=f"{kind}/{name} deixou de ser órfão desde o plano; gere um novo",
        )
    if not source.exists():
        raise SteamZeroError(
            "E-TX-STALE-PLAN", detail=f"{kind}/{name} sumiu desde o plano; gere um novo"
        )
    # O relpath do plano é a autoridade de endereço; divergir dele significa que
    # o plano fala de outro caminho, e nesse caso não se move nada.
    if _relpath(source) != str(item["relpath"]):
        raise SteamZeroError(
            "E-CONTENT-UNSAFE-PATH",
            detail=f"{kind}/{name} resolve para caminho diferente do planejado",
        )
    size, digest = measure(source)
    if digest != str(item["digest"]) or size != int(item["bytes"]):
        raise SteamZeroError(
            "E-TX-VERIFY-FAILED",
            detail=f"{kind}/{name} mudou desde o plano (digest ou tamanho); gere um novo",
        )
    return source


def _write_manifest(cleanup_dir: Path, payload: dict[str, Any]) -> Path:
    manifest = cleanup_dir / _MANIFEST_NAME
    fs.write_atomic_text(
        manifest,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        mode=_PRIVATE_FILE,
    )
    return manifest


def apply(plan_id: str, confirm_token: str) -> dict[str, Any]:
    """Move os artefatos do plano para uma quarentena isolada desta operação.

    Nunca deleta. Reconfere tudo antes de tocar em qualquer coisa e, se falhar
    no meio, devolve ao lugar o que já tinha movido. Quando nem a devolução
    funciona, o resultado é ``failed`` com o inventário exato do que ficou onde
    — jamais um sucesso otimista.
    """
    payload = _load_plan(plan_id, confirm_token, kind="cleanup")
    items: list[dict[str, Any]] = list(payload["items"])

    with lock.ResourceLock(_LOCK_RESOURCE):
        orphans = _current_orphans()
        sources = [_verify_item(item, orphans) for item in items]

        cleanup_id = ids.new_ulid()
        cleanup_dir = quarantine_for_cleanup(cleanup_id)
        if cleanup_dir.exists():
            raise SteamZeroError("E-STATE-INTEGRITY", detail=f"quarentena {cleanup_id} já existe")

        destinations: list[Path] = []
        for item in items:
            dest = cleanup_dir / str(item["kind"]) / str(item["name"])
            if dest.exists():
                raise SteamZeroError(
                    "E-STATE-INTEGRITY",
                    detail=f"destino de quarentena já ocupado: {item['kind']}/{item['name']}",
                )
            destinations.append(dest)

        quarantined_at = _now()
        moved: list[tuple[Path, Path]] = []
        try:
            for source, dest in zip(sources, destinations, strict=True):
                fs.ensure_dir(dest.parent)
                fs.move_tree(source, dest)
                moved.append((source, dest))
        except Exception as exc:
            restored, failures = _restore_moved(moved)
            if failures:
                return {
                    "schemaVersion": SCHEMA_VERSION,
                    "status": "failed",
                    "planId": plan_id,
                    "cleanupId": cleanup_id,
                    "detail": f"falha ao mover e ao devolver: {exc}",
                    "restored": restored,
                    "stillQuarantined": [
                        {"source": str(src), "quarantined": str(dst)} for src, dst in failures
                    ],
                }
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED" if failures else "E-TX-VERIFY-FAILED",
                detail=f"quarentena revertida sem efeito: {exc}",
            ) from exc

        retention_until = quarantined_at + timedelta(days=RETENTION_DAYS)
        manifest_payload = {
            "schemaVersion": SCHEMA_VERSION,
            "cleanupId": cleanup_id,
            "planId": plan_id,
            "quarantinedAt": _iso(quarantined_at),
            "retentionUntil": _iso(retention_until),
            "count": len(items),
            "totalBytes": int(payload["totalBytes"]),
            "items": items,
        }
        _write_manifest(cleanup_dir, manifest_payload)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "quarantined",
        "planId": plan_id,
        "cleanupId": cleanup_id,
        "quarantinedAt": _iso(quarantined_at),
        "retentionUntil": _iso(retention_until),
        "count": len(items),
        "totalBytes": int(payload["totalBytes"]),
    }


def _restore_moved(moved: list[tuple[Path, Path]]) -> tuple[int, list[tuple[Path, Path]]]:
    """Devolve ao lugar o que já foi movido. Retorna (devolvidos, falhas)."""
    restored = 0
    failures: list[tuple[Path, Path]] = []
    for source, dest in reversed(moved):
        try:
            fs.ensure_dir(source.parent)
            fs.move_tree(dest, source)
            restored += 1
        except OSError:
            failures.append((source, dest))
    return restored, failures


# ---------------------------------------------------------------------------
# Inspeção
# ---------------------------------------------------------------------------


def _load_manifest(cleanup_id: str) -> tuple[Path, dict[str, Any]]:
    cleanup_dir = quarantine_for_cleanup(cleanup_id)
    manifest = cleanup_dir / _MANIFEST_NAME
    if not manifest.is_file():
        raise SteamZeroError("E-STATE-INTEGRITY", detail=f"quarentena sem manifesto: {cleanup_id}")
    payload: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
    if int(payload.get("schemaVersion", 0)) != SCHEMA_VERSION:
        raise SteamZeroError(
            "E-STATE-INTEGRITY",
            detail=f"manifesto em schemaVersion {payload.get('schemaVersion')}",
        )
    return cleanup_dir, payload


def status(cleanup_id: str) -> dict[str, Any]:
    """Inspeção read-only de uma quarentena, ou do tombstone se já foi expurgada.

    Idempotente por construção: consultar não muda nada, e uma operação já
    expurgada continua respondendo — com ``purged``, não com "não existe", que
    o operador leria como perda de rastro.
    """
    tombstone = history_path(cleanup_id)
    if tombstone.is_file():
        payload: dict[str, Any] = json.loads(tombstone.read_text(encoding="utf-8"))
        payload["status"] = "purged"
        return payload

    cleanup_dir, manifest = _load_manifest(cleanup_id)
    now = _now()
    retention_until = _parse_iso(str(manifest["retentionUntil"]), field="retentionUntil")
    present = 0
    missing: list[str] = []
    for item in manifest["items"]:
        dest = cleanup_dir / str(item["kind"]) / str(item["name"])
        if dest.exists():
            present += 1
        else:
            missing.append(f"{item['kind']}/{item['name']}")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "quarantined",
        "cleanupId": cleanup_id,
        "planId": manifest.get("planId"),
        "quarantinedAt": manifest["quarantinedAt"],
        "retentionUntil": manifest["retentionUntil"],
        "retentionElapsed": now >= retention_until,
        "count": int(manifest["count"]),
        "totalBytes": int(manifest["totalBytes"]),
        "present": present,
        "missing": missing,
    }


# ---------------------------------------------------------------------------
# Restauração — duas fases, sem sobrescrever destino
# ---------------------------------------------------------------------------


def _persist_plan(payload: dict[str, Any]) -> dict[str, Any]:
    fs.ensure_dir(paths.plans_dir())
    fs.write_atomic_text(
        paths.plan_path(str(payload["planId"])),
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
    )
    return payload


def plan_restore(cleanup_id: str) -> dict[str, Any]:
    """Planeja devolver a quarentena às origens. Recusa se o destino foi reocupado."""
    cleanup_dir, manifest = _load_manifest(cleanup_id)
    entries: list[dict[str, Any]] = []
    conflicts: list[str] = []
    for item in manifest["items"]:
        kind, name = str(item["kind"]), str(item["name"])
        dest = cleanup_dir / kind / name
        if not dest.exists():
            continue
        origin = _source_for(kind, name)
        if origin.exists():
            # Sobrescrever é como se perde o dado novo: outra operação recriou
            # este id, e o conteúdo em quarentena não é mais o dono do caminho.
            conflicts.append(f"{kind}/{name}")
            continue
        entries.append({"kind": kind, "name": name, "relpath": item["relpath"]})

    created = _now()
    return _persist_plan(
        {
            "schemaVersion": SCHEMA_VERSION,
            "kind": "restore",
            "planId": ids.new_ulid(),
            "confirmToken": ids.new_ulid(),
            "cleanupId": cleanup_id,
            "createdAt": _iso(created),
            "expiresAt": _iso(created + timedelta(seconds=PLAN_TTL_SECONDS)),
            "count": len(entries),
            "conflicts": conflicts,
            "items": entries,
        }
    )


def apply_restore(plan_id: str, confirm_token: str) -> dict[str, Any]:
    """Devolve os itens planejados às origens, sem sobrescrever nada."""
    payload = _load_plan(plan_id, confirm_token, kind="restore")
    cleanup_id = str(payload["cleanupId"])
    cleanup_dir, _ = _load_manifest(cleanup_id)

    with lock.ResourceLock(_LOCK_RESOURCE):
        moved: list[tuple[Path, Path]] = []
        for item in payload["items"]:
            kind, name = str(item["kind"]), str(item["name"])
            dest = cleanup_dir / kind / name
            origin = _source_for(kind, name)
            if not dest.exists():
                continue
            if origin.exists():
                raise SteamZeroError(
                    "E-TX-STALE-PLAN",
                    detail=f"{kind}/{name} foi reocupado desde o plano; gere um novo",
                )
            fs.ensure_dir(origin.parent)
            fs.move_tree(dest, origin)
            moved.append((dest, origin))

    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "restored",
        "cleanupId": cleanup_id,
        "planId": plan_id,
        "count": len(moved),
    }


# ---------------------------------------------------------------------------
# Expurgo — irreversível, em duas fases, com retenção sem bypass
# ---------------------------------------------------------------------------


def plan_purge(cleanup_id: str) -> dict[str, Any]:
    """Planeja o expurgo definitivo. Recusa antes da retenção, sem exceção."""
    _, manifest = _load_manifest(cleanup_id)
    retention_until = _parse_iso(str(manifest["retentionUntil"]), field="retentionUntil")
    now = _now()
    if now < retention_until:
        remaining = retention_until - now
        raise SteamZeroError(
            "E-CONTENT-BUSY",
            detail=(
                f"retenção de {RETENTION_DAYS} dias ainda corre; faltam "
                f"{remaining.days}d {remaining.seconds // 3600}h até {manifest['retentionUntil']}"
            ),
        )

    created = _now()
    return _persist_plan(
        {
            "schemaVersion": SCHEMA_VERSION,
            "kind": "purge",
            "planId": ids.new_ulid(),
            "confirmToken": ids.new_ulid(),
            "cleanupId": cleanup_id,
            "createdAt": _iso(created),
            "expiresAt": _iso(created + timedelta(seconds=PLAN_TTL_SECONDS)),
            "count": int(manifest["count"]),
            "totalBytes": int(manifest["totalBytes"]),
            "retentionUntil": manifest["retentionUntil"],
            "irreversible": True,
        }
    )


def apply_purge(plan_id: str, confirm_token: str) -> dict[str, Any]:
    """Apaga a quarentena em definitivo, revalidando cada digest antes.

    Depois sobra apenas um tombstone: contagens, bytes, digest agregado e
    instantes. Nenhum caminho externo, credencial ou conteúdo — o registro
    prova o que houve sem reintroduzir o que foi apagado.
    """
    payload = _load_plan(plan_id, confirm_token, kind="purge")
    cleanup_id = str(payload["cleanupId"])
    cleanup_dir, manifest = _load_manifest(cleanup_id)

    retention_until = _parse_iso(str(manifest["retentionUntil"]), field="retentionUntil")
    if _now() < retention_until:
        raise SteamZeroError("E-CONTENT-BUSY", detail="retenção ainda corre; expurgo recusado")

    with lock.ResourceLock(_LOCK_RESOURCE):
        digests: list[str] = []
        purged_bytes = 0
        for item in manifest["items"]:
            dest = cleanup_dir / str(item["kind"]) / str(item["name"])
            if not dest.exists():
                continue
            size, digest = measure(dest)
            if digest != str(item["digest"]):
                raise SteamZeroError(
                    "E-TX-VERIFY-FAILED",
                    detail=(
                        f"{item['kind']}/{item['name']} mudou dentro da quarentena; "
                        "expurgo recusado"
                    ),
                )
            digests.append(digest)
            purged_bytes += size

        aggregate = fs.hash_bytes("\n".join(sorted(digests)).encode("utf-8"), algo="sha256")
        tombstone = {
            "schemaVersion": SCHEMA_VERSION,
            "cleanupId": cleanup_id,
            "quarantinedAt": manifest["quarantinedAt"],
            "retentionUntil": manifest["retentionUntil"],
            "purgedAt": _iso(_now()),
            "count": len(digests),
            "purgedBytes": purged_bytes,
            "aggregateDigest": aggregate,
        }
        target = history_path(cleanup_id)
        fs.ensure_dir(target.parent)
        fs.write_atomic_text(
            target,
            json.dumps(tombstone, ensure_ascii=False, indent=2, sort_keys=True),
            mode=_PRIVATE_FILE,
        )
        fs.remove_tree(cleanup_dir)

    return {**tombstone, "status": "purged", "planId": plan_id}
