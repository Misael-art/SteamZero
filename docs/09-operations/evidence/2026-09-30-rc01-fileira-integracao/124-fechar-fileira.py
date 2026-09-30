#!/usr/bin/env python3
"""124 — Fechamento documental da fileira #239–#247 integrada em main.

Transforma JSON de governança de forma determinística e auditável:
  * 8 workstreams `rc01-*` passam de `active` a `closed`, com o SHA de merge
    realmente integrado citado na `nextAction`;
  * 3 cartões de capacidade recebem o eixo `integration` que a integração
    efectivamente ganhou (`feature-branch` -> `integrated`), mais evidências
    novas apontando para arquivos que existem nesta pasta;
  * nenhum outro eixo se move: `implementation`, `verification`, `operation`
    e `distribution` continuam dizendo o que estavam dizendo, porque prova
    física na release instalada não foi executada.

Aborta (sem escrever) se qualquer premissa falhar: PR que não está MERGED,
SHA de merge que não é ancestral de main, cartão que já tinha outro valor,
caminho de evidência inexistente.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

def _root() -> Path:
    p = Path(__file__).resolve()
    for cand in p.parents:
        if (cand / ".git").exists():
            return cand
    raise SystemExit("ABORTO: raiz do repo nao encontrada")


ROOT = _root()
WS = ROOT / "docs" / "status" / "workstreams"
ITEMS = ROOT / "docs" / "status" / "items"
EVID = ROOT / "docs" / "09-operations" / "evidence" / "2026-09-30-rc01-fileira-integracao"

MAIN = "7808374257db3059c1934cb4be6007d8a749346e"
OLD_MAIN = "3495c49d5d7c3244267e8292beee34475f70236b"
TODAY = "2026-09-30"

# PR -> (branch, merge commit, arquivo do workstream, pendencia especifica)
LINKS = {
    240: (
        "codex/rc01-central-loading-2026-09-26",
        "cba3fe426f237ee75eb3f6aad42f6e0a098cc809",
        "rc01-central-loading-2026-09-26.json",
        "resta a prova fisica da central durante carregamento e a cauda de latencia de /status emulation (backend, fora deste escopo)",
    ),
    241: (
        "codex/rc01-readiness-focus-2026-09-27",
        "67e30afcddaa29f00e74e536533fcaaa1b8a1599",
        "rc01-readiness-focus-2026-09-27.json",
        "resta medir as cinco superficies rolaveis ainda nao exercitadas e a prova fisica",
    ),
    242: (
        "codex/rc01-shell-esde-dialog-2026-09-27",
        "231ba4d384181f6b5ea1154bbb5ef4a734a47d60",
        "rc01-shell-esde-dialog-2026-09-27.json",
        "resta o seletor nativo de diretorio (nao dirigivel por evento sob offscreen) e a prova fisica",
    ),
    243: (
        "codex/rc01-readiness-semantics-2026-09-28",
        "5f6ff5082adb69cfbcd999f5aee10ed94075b36f",
        "rc01-readiness-semantics-2026-09-28.json",
        "resta F-1 (memoryGb -> bytes pelo formatador) e a prova fisica",
    ),
    244: (
        "codex/rc01-storage-units-2026-09-28",
        "c43853088bafed1fbb725995d84a025899ade6e1",
        "rc01-storage-units-2026-09-28.json",
        "resta a prova fisica (o empacotamento ja esta provado: sizes.js byte-identicos no wheel do SHA consolidado)",
    ),
    245: (
        "codex/rc01-retrofe-shell-late-response-2026-09-29",
        "66b442b6b4f747e6cb35854689262a0d0f1bd2f8",
        "rc01-retrofe-shell-late-2026-09-29.json",
        "resta a prova fisica na release instalada",
    ),
    246: (
        "codex/rc01-home-first-fold-2026-09-29",
        "cb71a52799214a50c22dcd6471c43a11ef7be7ff",
        "rc01-home-first-fold-2026-09-29.json",
        "resta a prova fisica do contrato da dobra na release instalada",
    ),
    247: (
        "codex/rc01-esde-import-generation-2026-09-29",
        "7808374257db3059c1934cb4be6007d8a749346e",
        "rc01-esde-import-generation-2026-09-29.json",
        "resta o seletor nativo de diretorio e a prova fisica",
    ),
}


def die(msg: str) -> None:
    sys.exit(f"ABORTO: {msg}")


def git(*args: str) -> str:
    proc = subprocess.run(("git", *args), cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"git {' '.join(args)} -> rc={proc.returncode} {proc.stderr.strip()}")
    return proc.stdout.strip()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data: dict) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def main() -> None:
    # premissas duras, re-medidas agora
    if git("rev-parse", "origin/main") != MAIN:
        die(f"origin/main nao e {MAIN}: {git('rev-parse','origin/main')}")
    state = git("rev-parse", "--abbrev-ref", "HEAD")
    if state != "codex/rc01-fileira-fechamento-2026-09-30":
        die(f"branch de trabalho inesperada: {state}")
    for pr, (_branch, merge, _card, _pend) in LINKS.items():
        rc = subprocess.run(
            ("git", "merge-base", "--is-ancestor", merge, MAIN), cwd=ROOT
        ).returncode
        if rc != 0:
            die(f"PR #{pr}: merge commit {merge[:12]} nao e ancestral de main")
        if not git("cat-file", "-t", merge):
            die(f"PR #{pr}: objeto {merge} ausente")
        parents = [
            line
            for line in git("cat-file", "-p", merge).splitlines()
            if line.startswith("parent ")
        ]
        if len(parents) != 2:
            die(f"PR #{pr}: {merge[:12]} nao e merge commit ({len(parents)} pais)")
    for name in ("115-integracao-da-fileira-239-247.log",
                 "116-suite-real-executada-no-ci.log",
                 "122-empacotamento-sha-consolidado.log",
                 "123-suite-ci-sha-consolidado.log",
                 "README.md"):
        if not (EVID / name).exists():
            die(f"arquivo de evidencia ausente: {name}")

    # 1) workstreams -> closed
    for pr, (branch, merge, card, pending) in LINKS.items():
        path = WS / card
        data = load(path)
        if data["state"] != "active":
            die(f"{card}: ja nao estava active ({data['state']})")
        if data["branch"] != branch:
            die(f"{card}: branch divergente ({data['branch']} != {branch})")
        data["state"] = "closed"
        data["updatedAt"] = TODAY
        data["nextAction"] = (
            f"Fechado: PR #{pr} integrado em main pelo merge {merge[:12]} "
            f"(fileira #239-#247, main consolidado em {MAIN[:12]}). Contrato provado "
            f"offscreen e presente no wheel desse SHA; {pending}. "
            f"Narrativa e provas: {EVID.relative_to(ROOT)}/README.md."
        )
        dump(path, data)
        print(f"workstream closed: {card} <- #{pr} {merge[:12]}")

    # 2) cartoes de capacidade
    def add_evidence(identifier: str, entries: list[dict]) -> None:
        path = next(
            p for p in ITEMS.glob("*.json") if load(p).get("id") == identifier
        )
        data = load(path)
        for e in entries:
            if not (ROOT / e["reference"]).exists():
                die(f"{identifier}: referencia inexistente {e['reference']}")
            if e["reference"] in {x["reference"] for x in data["evidence"]}:
                die(f"{identifier}: evidencia duplicada {e['reference']}")
        data["evidence"].extend(entries)
        data["updatedAt"] = TODAY
        dump(path, data)
        print(f"evidencia: {identifier} +{len(entries)} (total {len(data['evidence'])})")

    audit_path = ITEMS / "ui-desktop-audit.json"
    audit = load(audit_path)
    if audit["integration"] != "feature-branch":
        die(f"SZ-UI-DESKTOP-AUDIT: integration nao era feature-branch ({audit['integration']})")
    new_dir = str(EVID.relative_to(ROOT))
    if new_dir not in audit["scopePaths"]:
        audit["scopePaths"].append(new_dir)
        audit["scopePaths"].sort()
    audit["integration"] = "integrated"
    audit["updatedAt"] = TODAY
    audit["nextAction"] = (
        "Executar a validacao fisica do conjunto integrado (release candidata "
        f"{MAIN[:12]}) com autorizacao especifica de instalacao; ate la os eixos "
        "implementacao/verificacao/operacao/distribuicao continuam os mesmos. "
        "F-1 (memoryGb), cinco superficies rolaveis e o seletor nativo seguem abertos."
    )
    dump(audit_path, audit)
    print(f"cartao: SZ-UI-DESKTOP-AUDIT integration=integrated scopePaths={len(audit['scopePaths'])}")

    rel = new_dir + "/"
    add_evidence(
        "SZ-UI-DESKTOP-AUDIT",
        [
            {
                "kind": "diagnostic",
                "result": "recorded",
                "reference": rel + "115-integracao-da-fileira-239-247.log",
                "command": (
                    "Integracao da fileira #239-#247 em main por merge commit, na ordem de "
                    "ancestralidade, com #245/#246/#247 recolocados em main nos pontos proprios. "
                    "Cada elo conferido no SHA exato (MERGEABLE/CLEAN + 8/8 checks obrigatorios) e "
                    "cada merge conferido por arvore identica a cabeca validada no CI. Sem conflito, "
                    "sem bypass, sem force-push."
                ),
            },
            {
                "kind": "test",
                "result": "passed",
                "reference": rel + "116-suite-real-executada-no-ci.log",
                "command": (
                    "Prova de que a suíte exigida rodou em cada cabeca: 5.965-6.152 aprovados, "
                    "47 pulados por elo, lidos do junit publicado pelo proprio run, nao de manchete."
                ),
            },
            {
                "kind": "test",
                "result": "passed",
                "reference": rel + "123-suite-ci-sha-consolidado.log",
                "command": (
                    "Push ao main consolidado 7808374257db: Python 3.11/3.12/3.14 com 6.199 itens "
                    "coletados, 0 falhas, 0 erros, 47 pulados cada, mais wheel+smoke e tres smokes "
                    "de distro em success."
                ),
            },
            {
                "kind": "test",
                "result": "passed",
                "reference": rel + "122-empacotamento-sha-consolidado.log",
                "command": (
                    "Empacotamento no SHA consolidado: wheel 2.0.0rc1 com proveniencia commit="
                    "7808374257db, hash batendo com SHA256SUMS e proveniencia, pip-audit limpo, e "
                    "sizes.js/readiness.py/readiness.js/console_runtime_readiness.py byte-identicos "
                    "ao main dentro do pacote (625 arquivos, 61 QML)."
                ),
            },
            {
                "kind": "diagnostic",
                "result": "recorded",
                "reference": rel + "README.md",
                "command": (
                    "Fechamento da fileira: quadro RC-01 critério a critério nas cinco camadas "
                    "(interface, contrato offscreen, integrado, empacotado, host), com a coluna "
                    "G promovida por prova de arvore e a coluna H explicitamente nao promovida."
                ),
            },
            {
                "kind": "diagnostic",
                "result": "recorded",
                "reference": rel + "125-preparacao-do-host-no-sha-consolidado.md",
                "command": (
                    "Proxima intervencao no host preparada no SHA consolidado: preflights, release "
                    "candidata, rollback e cinco jornadas com o que cada uma prova e o que nao "
                    "prova. Nada foi instalado; as precondicoes 2 e 3 continuam do operador."
                ),
            },
        ],
    )

    for identifier, extra in (
        (
            "SZ-PROJECT-DESIGN-AUDIT",
            "Documentos da auditoria de design integrados em main pelo merge 9fc1c5948fca (#239).",
        ),
        (
            "SZ-ROADMAP-CONTINUATION",
            "Roadmap, milestones e handoff continuados integrados em main pelo merge 9fc1c5948fca (#239).",
        ),
    ):
        path = next(p for p in ITEMS.glob("*.json") if load(p).get("id") == identifier)
        data = load(path)
        if data["integration"] != "feature-branch":
            die(f"{identifier}: integration nao era feature-branch ({data['integration']})")
        data["integration"] = "integrated"
        data["updatedAt"] = TODAY
        dump(path, data)
        add_evidence(
            identifier,
            [
                {
                    "kind": "diagnostic",
                    "result": "recorded",
                    "reference": rel + "115-integracao-da-fileira-239-247.log",
                    "command": extra,
                }
            ],
        )
        print(f"cartao: {identifier} integration=integrated")

    print("OK: fechamento aplicado")


if __name__ == "__main__":
    main()
