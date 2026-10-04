# SPDX-License-Identifier: GPL-3.0-or-later
"""O gate de unidades tem de ser verde em qualquer locale — inclusive o do CI.

Duas exigências legíveis, cada uma com o defeito que ela impede:

1. ``AUDIT.md:124`` pede "unidades localizadas". Uma unidade localizada é a
   leitura que o locale EM VIGOR dita, não uma leitura que o autor do teste
   escolheu. O harness já pinou ``Qt.locale("pt_BR")`` e comparou as saídas
   contra esse pino: ficou verde na máquina do autor (pt_BR) e vermelho nas
   cabeças do CI, porque ``ci/qml-visual/Containerfile:58-59`` fixa
   ``LC_ALL=C.UTF-8`` e ``environment.lock.json:26`` tranca o mesmo locale.
   Um gate que só passa no fuso do desenvolvedor não é um gate.

2. Rodar o mesmo harness sob dois locales só vale se os dois contextos forem
   de fato distintos. Se o ``LC_ALL`` não chegar ao Qt, a matriz verifica a
   mesma formatação duas vezes e continua verde. Por isso o teste exige que o
   harness informe o locale que usou E que os separadores dos dois casos
   difiram — a prova de não vacuidade, não um detalhe de implementação.

Nada aqui fixa a cor, o texto ou o separador de um locale específico: o que se
verifica é a delegação.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

QML = shutil.which("qml6")
ROOT = Path(__file__).resolve().parents[2]
HARNESS = "tests/qml/check_storage_units.qml"

DIAG_VISUAL_ENVIRONMENT = "QML-VISUAL-ENVIRONMENT-001"

#: (LC_ALL/LANG do processo, nome de locale que o harness deve reportar)
#:
#: ``C.UTF-8`` é o locale congelado da imagem do gate visual; ``pt_BR.UTF-8``
#: é o locale do produto. Qt resolve o nome por conta própria (medido:
#: ``fr_FR.UTF-8`` e ``de_DE.ISO-8859-1`` também são honrados sem dados do
#: glibc), então o caso não depende da imagem ter o locale instalado.
LOCAIS = (("C.UTF-8", "C"), ("pt_BR.UTF-8", "pt_BR"))

#: O prefixo muda entre host e CI: ``QT_MESSAGE_PATTERN`` faz o Qt publicar
#: ``qml|FAIL:``, enquanto o host publica ``qml: FAIL:``. Extrair por
#: substring, nunca por prefixo.
MARCADOR_FALHA = "FAIL:"
MARCADOR_LOCALE = "check_storage_units locale="
MARCADOR_VEREDITO = "check_storage_units:"

pytestmark = pytest.mark.visual


def _ambiente(locale_nome: str) -> dict[str, str]:
    env = os.environ.copy()
    # LANGUAGE (GNU) sobrepõe LC_ALL no Qt; um host pt_BR vazaria para a matriz.
    env.pop("LANGUAGE", None)
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


def _linhas(saida: str, marcador: str) -> list[str]:
    return [linha.strip() for linha in saida.splitlines() if marcador in linha]


def _executar(locale_nome: str) -> subprocess.CompletedProcess[str]:
    assert QML is not None, f"{DIAG_VISUAL_ENVIRONMENT}: qml6 ausente; gate visual não verificável"
    return subprocess.run(
        [str(QML), HARNESS],
        cwd=ROOT,
        env=_ambiente(locale_nome),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _separador_diagnosticado(saida: str) -> Iterator[str]:
    """O separador que o harness informou, se informou."""
    for linha in _linhas(saida, MARCADOR_LOCALE):
        trecho = linha.split(MARCADOR_LOCALE, 1)[1]
        campos = dict(par.split("=", 1) for par in trecho.split() if "=" in par)
        if "decimal" in campos:
            yield campos["decimal"].strip('"')


@pytest.mark.parametrize(("locale_nome", "esperado"), LOCAIS)
def test_gate_de_unidades_e_verde_sob_cada_locale(locale_nome: str, esperado: str) -> None:
    """Nenhum pino de locale pode transformar o gate em vermelho do CI."""
    completed = _executar(locale_nome)
    saida = completed.stdout + completed.stderr
    falhas = _linhas(saida, MARCADOR_FALHA)
    veredito = _linhas(saida, MARCADOR_VEREDITO)

    assert veredito, f"LC_ALL={locale_nome}: o harness não publicou veredito\n{saida[-2000:]}"
    diagnostico = "\n".join(falhas[:8]) if falhas else "(nenhum FAIL publicado)"
    assert completed.returncode == 0, (
        f"LC_ALL={locale_nome}: gate de unidades reprovado ({completed.returncode}); "
        f"veredito={veredito[-1]}\n{diagnostico}"
    )
    assert not falhas, f"LC_ALL={locale_nome}: gate publicou falhas\n{diagnostico}"

    locales = _linhas(saida, MARCADOR_LOCALE)
    assert locales, f"LC_ALL={locale_nome}: harness não informou o locale usado"
    assert f"locale={esperado}" in locales[0], (
        f"LC_ALL={locale_nome}: o harness rodou sob {locales[0]!r}, não sob {esperado!r}; "
        "a matriz não estaria exercendo o locale pedido"
    )


def test_a_matriz_exerce_dois_contextos_de_formatacao_distintos() -> None:
    """Prova de não vacuidade: separadores diferentes, não o mesmo caso duas vezes."""
    observado: dict[str, str] = {}
    for locale_nome, esperado in LOCAIS:
        completed = _executar(locale_nome)
        saida = completed.stdout + completed.stderr
        assert completed.returncode == 0, (
            f"LC_ALL={locale_nome}: o gate reprovou antes da comparação"
        )
        locale_reportado = _linhas(saida, MARCADOR_LOCALE)
        assert locale_reportado and f"locale={esperado}" in locale_reportado[0], (
            f"LC_ALL={locale_nome}: harness reportou {locale_reportado!r}, esperado {esperado!r}"
        )
        separadores = list(_separador_diagnosticado(saida))
        assert separadores, f"LC_ALL={locale_nome}: harness não publicou o separador em uso"
        observado[esperado] = separadores[0]

    assert len(set(observado.values())) == len(observado), (
        f"os dois locales produziram o mesmo separador ({observado}): a matriz verificou a "
        "mesma formatação duas vezes e não prova delegação ao locale em vigor"
    )
