"""Bateria de mutações do gate de unidades (UX-04, rodada 2).

Ancoragem: os mutantes da rodada anterior falharam porque `Math.pow(1024, ...)` e
`toLocaleString(Qt.locale())` também aparecem no COMENTÁRIO de `sizes.js` (linha
19), e `replace(..., 1)` atingiu o comentário — um mutante que não toca o código
é um verde sem informação. Aqui cada âncora é o corpo da função.

Para cada mutante: aplica, roda o harness sob os dois locales da matriz, registra
reprovação/absorção, restaura e confere sha256. `esperado` diz o que o gate tem de
ver naquele locale; um `VAZIO` é pino vacuo.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
QML = shutil.which("qml6")
HARNESS = "tests/qml/check_storage_units.qml"
SIZES = ROOT / "src/steamzero/ui/qml/sizes.js"
MAIN = ROOT / "src/steamzero/ui/qml/Main.qml"
LOCAIS = ("C.UTF-8", "pt_BR.UTF-8")

# Corpo real de sizes.bytes (linha 50), não a menção do comentário.
DIVISAO = "return (total / Math.pow(1024, expoente)).toLocaleString(Qt.locale())"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def ambiente(locale_nome: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "QT_FORCE_STDERR_LOGGING": "1",
            "QT_LOGGING_RULES": "",
            "QT_QPA_PLATFORM": "offscreen",
            "QML_DISABLE_DISK_CACHE": "1",
            "LANG": locale_nome,
            "LC_ALL": locale_nome,
        }
    )
    return env


def rodar(locale_nome: str) -> tuple[int, int, str]:
    completed = subprocess.run(
        [QML, HARNESS], cwd=ROOT, env=ambiente(locale_nome),
        capture_output=True, text=True, timeout=150, check=False,
    )
    saida = completed.stdout + completed.stderr
    falhas = [l for l in saida.splitlines() if "FAIL:" in l]
    veredito = [l for l in saida.splitlines() if "check_storage_units:" in l]
    if falhas:
        exemplo = falhas[0].replace("qml: FAIL:", "").replace("qml|FAIL:", "").strip()[:120]
    else:
        exemplo = (veredito[-1].replace("qml: ", "").replace("qml|", "").strip()
                   if veredito else "SEM VEREDITO")
    return completed.returncode, len(falhas), exemplo


def mutante(
    nome: str, alvo: Path, de: str, para: str, esperado: dict[str, bool], nota: str
) -> None:
    original = alvo.read_text(encoding="utf-8")
    if original.count(de) != 1:
        print(f"{nome}: ÂNCORA INVALIDA ({original.count(de)} ocorrências) — não executado")
        return
    hash_antes = sha256(alvo)
    alvo.write_text(original.replace(de, para, 1), encoding="utf-8")
    print(f"{nome}  [{nota}]")
    try:
        for locale_nome in LOCAIS:
            rc, qtd, exemplo = rodar(locale_nome)
            reprovado = rc != 0
            sinal = "OK" if esperado[locale_nome] == reprovado else "PIN VAZIO"
            print(
                f"   {locale_nome:<12} rc={rc} falhas={qtd:<3} "
                f"{'REPROVADO' if reprovado else 'VERDE'} "
                f"esperado={'reprovar' if esperado[locale_nome] else 'verde'} -> {sinal}"
            )
            if exemplo:
                print(f"      {exemplo}")
    finally:
        alvo.write_text(original, encoding="utf-8")
        if sha256(alvo) != hash_antes:
            print(f"{nome}: RESTAURACAO FALHOU em {alvo.name}", file=sys.stderr)
            sys.exit(2)


def ensaio_matriz(nome: str, de: str, para: str, nota: str) -> None:
    """Mutante do próprio harness: a matriz de locales tem de reprovar a regressão.

    Este é o teste-do-teste. O defeito original não era da produção, era do gate
    (pino `Qt.locale("pt_BR")`), então nenhum mutante de `sizes.js` o reproduz —
    só a volta do pino, e quem deve pegá-la é
    `tests/integration/test_storage_units_locale_matrix.py`.
    """
    harness_path = ROOT / HARNESS
    original = harness_path.read_text(encoding="utf-8")
    if original.count(de) != 1:
        print(f"{nome}: ÂNCORA INVALIDA ({original.count(de)}) — não executado")
        return
    hash_antes = sha256(harness_path)
    harness_path.write_text(original.replace(de, para, 1), encoding="utf-8")
    print(f"{nome}  [{nota}]")
    try:
        env = os.environ.copy()
        env.update({"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "QT_LOGGING_RULES": ""})
        completed = subprocess.run(
            [str(ROOT / ".venv/bin/python"), "-m", "pytest",
             "tests/integration/test_storage_units_locale_matrix.py", "-q"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=600, check=False,
        )
    finally:
        harness_path.write_text(original, encoding="utf-8")
        if sha256(harness_path) != hash_antes:
            print(f"{nome}: RESTAURACAO FALHOU", file=sys.stderr)
            sys.exit(2)
    saida = completed.stdout + completed.stderr
    resumo = [l for l in saida.splitlines() if " passed" in l or " failed" in l]
    print(f"   pytest rc={completed.returncode} :: {resumo[-1] if resumo else saida[-200:]}")


def main() -> int:
    print(f"qml={QML} harness={HARNESS}")
    ancoras = {SIZES: sha256(SIZES), MAIN: sha256(MAIN)}
    print("baseline (árvore real):")
    for locale_nome in LOCAIS:
        rc, qtd, exemplo = rodar(locale_nome)
        print(f"   {locale_nome:<12} rc={rc} falhas={qtd} {exemplo}")
    print(f"   anchors: sizes.js sha={sha256(SIZES)} Main.qml sha={sha256(MAIN)}")

    mutante(
        "M1 locale em PIN no formatador", SIZES,
        DIVISAO, DIVISAO.replace("Qt.locale()", 'Qt.locale("en_US")'),
        {"C.UTF-8": False, "pt_BR.UTF-8": True},
        "delegação ao locale em vigor",
    )
    mutante(
        "M2 formatador sem locale (toFixed)", SIZES,
        DIVISAO, DIVISAO.replace(".toLocaleString(Qt.locale())", ".toFixed(2)"),
        {"C.UTF-8": False, "pt_BR.UTF-8": True},
        "o separador vem do aparelho, não do autor",
    )
    mutante(
        "M3 divisor decimal sob rótulo IEC", SIZES,
        DIVISAO, DIVISAO.replace("Math.pow(1024, expoente)", "Math.pow(1000, expoente)"),
        {"C.UTF-8": True, "pt_BR.UTF-8": True},
        "oráculo de grandeza (novo pino desta rodada)",
    )
    mutante(
        "M4 rótulo GB sobre divisor 1024", SIZES,
        'var _unidades = ["B", "KiB", "MiB", "GiB"',
        'var _unidades = ["B", "KiB", "MiB", "GB"',
        {"C.UTF-8": True, "pt_BR.UTF-8": True},
        "rótulo binário + oráculo",
    )
    mutante(
        "M5 ausência vira zero", SIZES,
        'var ABSENTE = "—"', 'var ABSENTE = "0 B"',
        {"C.UTF-8": True, "pt_BR.UTF-8": True},
        "não medido ≠ medido como zero",
    )
    mutante(
        "M6 andar sem normalizar (mantissa < 1)", SIZES,
        "    if (total < 1024)", "    if (total < 0)",
        {"C.UTF-8": True, "pt_BR.UTF-8": True},
        "nada some abaixo da menor unidade",
    )
    mutante(
        "M7 prosa do shell com texto pronto", MAIN,
        ".arg(Sizes.bytes(result.bytesRead))", '.arg("1,00 GiB")',
        {"C.UTF-8": True, "pt_BR.UTF-8": False},
        "prosa roteia pelo formatador único; em pt_BR o texto pronto é a "
        "leitura correta, então o caso é verde por definição",
    )
    ensaio_matriz(
        "H1 o gate volta a pinar um locale",
        "    property var locale: Qt.locale()",
        '    property var locale: Qt.locale("pt_BR")',
        "defeito original da rodada: verde no fuso do autor, vermelho no CI "
        "(LC_ALL=C.UTF-8 fixado pela imagem do gate visual)",
    )

    print("\nrestauração:")
    divergente = False
    for alvo, esperado_hash in ancoras.items():
        atual = sha256(alvo)
        sinal = "identico" if atual == esperado_hash else "DIVERGENTE"
        divergente = divergente or atual != esperado_hash
        print(f"   {alvo.name}: {atual} vs baseline {esperado_hash} -> {sinal}")
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True,
                            capture_output=True, check=False).stdout
    for linha in status.splitlines():
        print(f"   git: {linha}")
    if divergente:
        print("ARVORE NAO RESTAURADA", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
