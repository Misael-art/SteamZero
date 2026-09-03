# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Aquisição e instalação transacional de temas ES-DE.

O operador pediu que temas tivessem o mesmo rigor dos componentes: transação com
rollback completo, **preservando os assets compartilhados** para não quebrar
dependências de outros temas. Este módulo é onde as duas exigências se encontram,
e elas se resolvem juntas por causa de uma propriedade do store.

**Por que o rollback aqui é simples.** Como ``theme_assets`` guarda blobs por
conteúdo e a posse é derivada dos manifestos instalados, a instalação de um tema
NUNCA sobrescreve nem remove um blob: no pior caso ela adiciona blobs que passam
a não ter dono. Desfazer, então, é remover o manifesto e restaurar o anterior —
duas operações de um arquivo só. Nenhum asset precisa ser restaurado porque
nenhum foi destruído, e um blob que outro tema referencia continua referenciado.
O espaço eventualmente ocioso é recuperado por ``collect_garbage``, que é
explícito e seguro de rodar a qualquer momento.

Um contador de referências teria feito o rollback ter que desfazer incrementos,
e um incremento perdido no meio de uma queda corromperia a contabilidade
silenciosamente. É a razão de ele não existir.

**Ingestão em fluxo.** O tarball tem de 60 a 150 MB, quase tudo binário. Cada
membro vai do tar direto ao store, sem materializar a árvore: gasta metade do
espaço e unifica na entrada o que o próprio pacote repete.

**Sobre a economia, com o número medido.** Entre xmb-menu e nso-menu, dois temas
ES-DE reais, os blobs em comum foram **um**. Temas ES-DE trazem a própria arte,
as próprias fontes e o próprio fundo; eles não dividem acervo. A deduplicação
paga em dois casos que existem de verdade — duplicatas dentro do mesmo pacote
(6,1 MB de 80 MB no nso-menu) e duas versões do mesmo tema, onde a maior parte
dos arquivos é idêntica — mas prometer economia entre temas distintos seria
contrariar a medição.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, log, paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.net import HttpClient, fetch_bytes
from steamzero.core.safetar import SafeTarLimits, iter_members
from steamzero.domain.theme_assets import ALLOWED_SUFFIXES, ThemeAssetStore, digest_bytes
from steamzero.domain.theme_sources import ThemeSource

#: Teto do tarball. O maior tema licenciado medido em 2026-09-03 (iconic) fica
#: bem abaixo; o teto existe para que um endereço trocado não vire download sem
#: fim, não para apertar os temas conhecidos.
MAX_ARCHIVE_BYTES = 320 * 1024 * 1024

_INGEST_LIMITS = SafeTarLimits(
    max_entries=20_000,
    max_total_bytes=512 * 1024 * 1024,
    max_entry_bytes=64 * 1024 * 1024,
    max_depth=16,
)


@dataclass
class AcquisitionReport:
    """O que entrou, o que já existia e o que foi recusado.

    A economia é contada em DUAS colunas separadas, e a separação foi paga com
    uma conclusão errada: um único contador de "deduplicado" fez o nso-menu
    parecer ter reaproveitado 6,1 MB do xmb-menu já instalado. Medindo blob a
    blob depois, os dois temas compartilhavam **um** arquivo. Os 6,1 MB eram o
    nso deduplicando contra si mesmo — 53 arquivos repetidos dentro do próprio
    pacote.

    As duas economias são reais e têm causas diferentes:

    - ``bytes_repeated_in_package``: o pacote traz o mesmo arquivo mais de uma
      vez. Acontece sempre, é interno e não diz nada sobre outros temas.
    - ``bytes_shared_with_installed``: o arquivo já estava no store por causa de
      OUTRO tema. É esta que sustenta a promessa de compartilhamento, e é a que
      precisa ser olhada antes de afirmar que dois temas dividem assets.

    Somá-las num número só é o que transforma uma medição em alegação errada.
    """

    theme_id: str
    files: int = 0
    bytes_ingested: int = 0
    bytes_repeated_in_package: int = 0
    bytes_shared_with_installed: int = 0
    skipped: int = 0
    assets: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "themeId": self.theme_id,
            "files": self.files,
            "bytesIngested": self.bytes_ingested,
            "bytesRepeatedInPackage": self.bytes_repeated_in_package,
            "bytesSharedWithInstalled": self.bytes_shared_with_installed,
            "skipped": self.skipped,
            "assetCount": len(self.assets),
        }


def ingest_archive(
    archive: Path,
    source: ThemeSource,
    store: ThemeAssetStore,
) -> AcquisitionReport:
    """Move o conteúdo do tarball para o store, um membro por vez.

    Devolve o mapa ``caminho lógico -> digest`` que vira o manifesto do tema.

    O que já estava no store é classificado por ORIGEM: se este mesmo pacote já
    o trouxe, é repetição interna; se não, veio de outro tema. Sem separar as
    duas, um pacote com muitas duplicatas próprias parece estar reaproveitando
    o acervo alheio — foi exatamente o erro cometido em 2026-09-03.
    """
    report = AcquisitionReport(theme_id=source.id)
    # Digests que ESTE pacote já entregou, para distinguir repetição interna de
    # compartilhamento com o que já estava instalado.
    seen_in_package: set[str] = set()
    for member in iter_members(
        archive,
        limits=_INGEST_LIMITS,
        strip_components=source.root_prefix_components,
        allowed_suffixes=ALLOWED_SUFFIXES,
    ):
        digest = digest_bytes(member.payload)
        already_stored = store.has(digest)
        repeated_here = digest in seen_in_package
        try:
            stored = store.put(member.path, member.payload)
        except SteamZeroError as exc:
            if exc.code != "E-THEME-UNSAFE":
                raise
            # Extensão fora da fronteira: pular é o correto, e a contagem
            # mantém visível que algo do pacote não entrou.
            report.skipped += 1
            continue
        seen_in_package.add(stored.digest)
        report.assets[member.path] = stored.digest
        report.files += 1
        if repeated_here:
            report.bytes_repeated_in_package += member.size
        elif already_stored:
            report.bytes_shared_with_installed += member.size
        else:
            report.bytes_ingested += member.size
    if not report.assets:
        raise SteamZeroError(
            "E-CONTENT-INCOMPLETE",
            detail=f"o pacote de '{source.id}' não trouxe nenhum arquivo utilizável",
        )
    return report


def download_archive(
    source: ThemeSource,
    *,
    operation_id: str,
    http_client: HttpClient | None = None,
    expected_sha256: str | None = None,
) -> Path:
    """Baixa o tarball do commit fixado, para o staging da operação.

    ``expected_sha256`` é opcional **por medição**: os tarballs das duas forges
    se mostraram byte-estáveis entre downloads (verificado em 2026-09-03), mas o
    que garante o conteúdo é o commit, que é o próprio hash da árvore no git.
    Quando o checksum é declarado ele é exigido; sem ele, a identidade continua
    ancorada no commit e não no empacotamento, que a forge pode mudar.
    """
    payload = fetch_bytes(source.archive_url, max_bytes=MAX_ARCHIVE_BYTES, client=http_client)
    if expected_sha256:
        digest = digest_bytes(payload)
        if digest != expected_sha256:
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE",
                detail=f"checksum do pacote de '{source.id}' não confere",
            )
    return fs.stage_bytes(operation_id, "theme.tar.gz", payload)


def build_manifest(source: ThemeSource, report: AcquisitionReport) -> dict[str, Any]:
    """Manifesto do tema instalado: identidade, crédito e o mapa de assets.

    ``credits`` viaja junto porque CC-BY-NC-SA exige atribuição e três dos cinco
    temas curados são obras derivadas — publicar só o dono do repositório
    apagaria quem fez o trabalho original.
    """
    return {
        "schemaVersion": 1,
        "kind": "steamzero-theme-v1",
        "id": source.id,
        "name": source.name,
        "version": source.commit[:12],
        "author": source.author,
        "credits": list(source.credits),
        "license": source.license_id,
        "homepage": source.homepage,
        "origin": {
            "family": source.family,
            "forge": source.forge,
            "repo": source.repo,
            "commit": source.commit,
        },
        "assets": {path: {"digest": digest} for path, digest in sorted(report.assets.items())},
    }


class ThemeTransaction:
    """Instalação e remoção de tema com desfazer completo.

    A transação cobre exatamente um arquivo — o ``theme.json`` do tema — porque é
    esse arquivo que define o que está instalado. Os blobs ficam fora dela de
    propósito: eles são imutáveis e compartilhados, e incluí-los na transação
    obrigaria a decidir, no rollback, se um blob "pertencia" a esta operação. Essa
    pergunta não tem resposta correta quando dois temas usam o mesmo arquivo, e é
    exatamente onde um contador de referências erra.
    """

    def __init__(self, themes_root: Path, store: ThemeAssetStore) -> None:
        self._root = themes_root
        self._store = store

    def _manifest_path(self, theme_id: str) -> Path:
        directory = self._root / theme_id
        if directory.resolve().parent != self._root.resolve():
            raise SteamZeroError("E-THEME-UNSAFE", detail=f"id de tema inválido: {theme_id!r}")
        return directory / "theme.json"

    def install(
        self,
        source: ThemeSource,
        report: AcquisitionReport,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """Publica o manifesto, guardando o anterior para permitir o desfazer."""
        manifest_path = self._manifest_path(source.id)
        if manifest_path.is_symlink():
            raise SteamZeroError("E-THEME-UNSAFE", detail="destino de manifesto é symlink")

        previous: bytes | None = None
        if manifest_path.is_file():
            if not force:
                raise SteamZeroError(
                    "E-THEME-DOWNLOAD-FAILED",
                    detail=f"tema '{source.id}' já instalado; confirme a substituição",
                )
            previous = manifest_path.read_bytes()

        manifest = build_manifest(source, report)
        # Verificar ANTES de publicar: um manifesto que aponta para blob ausente
        # instalaria um tema quebrado, e o defeito só apareceria ao renderizar.
        verification = self._store.verify(entry["digest"] for entry in manifest["assets"].values())
        if not verification["ok"]:
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE",
                detail=(
                    f"o store não tem todos os assets de '{source.id}': "
                    f"{len(verification['missing'])} ausente(s), "
                    f"{len(verification['corrupt'])} corrompido(s)"
                ),
            )

        operation_id = ids.new_ulid()
        undo_path: Path | None = None
        if previous is not None:
            undo_path = fs.stage_bytes(operation_id, "previous-theme.json", previous)

        fs.write_atomic_text(
            manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
        log.get_logger().info("theme_acquire.installed", theme=source.id, operation=operation_id)
        return {
            "themeId": source.id,
            "name": source.name,
            "version": manifest["version"],
            "license": source.license_id,
            "credits": list(source.credits),
            "operationId": operation_id,
            "assetCount": len(manifest["assets"]),
            "replaced": previous is not None,
            "undoPath": str(undo_path) if undo_path else "",
            "activated": False,
        }

    def rollback(self, theme_id: str, operation_id: str) -> dict[str, Any]:
        """Desfaz uma instalação, restaurando o manifesto anterior se havia um.

        Nenhum blob é tocado. É isso que garante que desfazer a instalação de um
        tema não invalide um asset que outro tema referencia — a preocupação que
        motivou o desenho.
        """
        manifest_path = self._manifest_path(theme_id)
        undo_path = paths.staging_for(operation_id) / "previous-theme.json"

        if undo_path.is_file():
            fs.write_atomic(manifest_path, undo_path.read_bytes())
            restored = True
        else:
            # Não havia versão anterior: desfazer é voltar a não ter o tema.
            fs.remove_file(manifest_path)
            restored = False
        return {
            "themeId": theme_id,
            "operationId": operation_id,
            "restoredPrevious": restored,
            "assetsPreserved": True,
        }

    def uninstall(self, theme_id: str) -> dict[str, Any]:
        """Remove o tema sem tocar nos blobs.

        O espaço não volta aqui, e isso é deliberado: o que ficou ocioso pode ser
        de outro tema que ainda não foi lido. ``collect_garbage`` responde essa
        pergunta olhando todos os manifestos de uma vez, que é a única forma de
        respondê-la corretamente.
        """
        manifest_path = self._manifest_path(theme_id)
        if not manifest_path.is_file():
            raise SteamZeroError(
                "E-THEME-NOT-FOUND", detail=f"tema '{theme_id}' não está instalado"
            )
        fs.remove_file(manifest_path)
        return {"themeId": theme_id, "removed": True, "assetsPreserved": True}


def acquire_and_install(
    source: ThemeSource,
    store: ThemeAssetStore,
    themes_root: Path,
    *,
    force: bool = False,
    http_client: HttpClient | None = None,
    expected_sha256: str | None = None,
    download: Callable[..., Path] | None = None,
) -> dict[str, Any]:
    """Fluxo completo: baixa, ingere em fluxo e publica o manifesto.

    O staging é limpo em qualquer desfecho MENOS quando a instalação venceu: o
    ``previous-theme.json`` guardado ali é o que permite o rollback, e apagá-lo
    junto com o tarball tornaria a operação irreversível no exato momento em que
    ela passa a precisar ser reversível.
    """
    operation_id = ids.new_ulid()
    fetch = download or download_archive
    archive = fetch(
        source,
        operation_id=operation_id,
        http_client=http_client,
        expected_sha256=expected_sha256,
    )
    try:
        report = ingest_archive(archive, source, store)
        transaction = ThemeTransaction(themes_root, store)
        result = transaction.install(source, report, force=force)
    finally:
        # O tarball já não é necessário depois da ingestão, com ou sem sucesso.
        fs.remove_file(archive)
    return {**result, "acquisition": report.to_dict()}
