# SPDX-License-Identifier: GPL-3.0-or-later
"""UX-05/UX-07 — o diálogo "Importar tema ES-DE" em viewport compacto.

Cinco testes em três papéis, espelhando o gate da fatia RetroFE para que as duas
provas sejam comparáveis:

* As três guardas de intenção rodam **sempre**, inclusive onde não há Qt. São a
  guarda contra "consertar" a reprovação trocando o evento real por chamada de
  volta, por atraso fixo ou por rolagem manual: contrato de viewport só vale se
  medido com teclado/click reais, espera observável com limite e falha, e captura
  que existe e só usa dados locais.
* ``test_dialogo_esde_fica_alcancavel_em_qualquer_viewport`` (``visual``) executa
  o harness QtTest com ``qmltestrunner`` no runtime do projeto e reprova se
  qualquer um dos 11 cenários falhar.
* ``test_capturas_de_evidencia_dos_dois_viewports`` (``visual``) roda a cena de
  captura para o diretório temporário do pytest — fora do checkout — e confere
  que cada imagem existe e tem o tamanho do viewport pedido. A leitura das
  imagens é humana, na pasta de evidência; nada aqui afirma que a release
  instalada no host foi testada.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests" / "qml" / "check_esde_import_dialog_compact_viewport.qml"
CAPTURE = ROOT / "tests" / "qml" / "capture_esde_import_viewport.qml"

CAPTURE_NAMES = (
    "1-compacto-acoes-e-corpo",
    "2-compacto-listagem-24-esquemas",
    "3-compacto-rodape-fixo-com-campo-de-nome-focado",
    "4-compacto-relatorio-extenso",
    "5-largo-relatorio-extenso",
)


def _qt6_binaries() -> tuple[str | None, str | None]:
    runner = next(
        (
            str(candidate)
            for candidate in (
                Path("/usr/lib/qt6/bin/qmltestrunner"),
                Path("/usr/lib64/qt6/bin/qmltestrunner"),
            )
            if candidate.is_file() and os.access(candidate, os.X_OK)
        ),
        shutil.which("qmltestrunner6"),
    )
    qml = next(
        (
            str(candidate)
            for candidate in (
                Path("/usr/lib/qt6/bin/qml"),
                Path("/usr/lib64/qt6/bin/qml"),
            )
            if candidate.is_file() and os.access(candidate, os.X_OK)
        ),
        shutil.which("qml6"),
    )
    return runner, qml


RUNNER, QML = _qt6_binaries()


def _environment() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QT_FORCE_STDERR_LOGGING": "1",
            "QT_LOGGING_RULES": "",
        }
    )
    return env


def _harness_source() -> str:
    assert HARNESS.is_file(), f"{HARNESS} não existe"
    return HARNESS.read_text(encoding="utf-8")


def test_o_harness_de_contrato_nao_finge_os_eventos() -> None:
    """Roda sem Qt: garante que a prova é de comportamento, não de API interna."""
    source = _harness_source()
    assert "Item {" in source, "QuickTest hospeda o caso em QQuickView; raiz Window é rejeitada"
    assert "ThemeEditorPanel {" in source, "o harness precisa carregar o painel real"
    assert "TestCase {" in source and "when: windowShown" in source, (
        "sem QtTest com windowShown não há janela exibida nem evento de teclado real"
    )
    for tecla in (
        "keyClick(Qt.Key_Down)",
        "keyClick(Qt.Key_Up)",
        "keyClick(Qt.Key_Tab)",
        "keyClick(Qt.Key_Backtab)",
        "keyClick(Qt.Key_Left)",
        "keyClick(Qt.Key_Backspace)",
        "keyClick(Qt.Key_Escape)",
    ):
        assert tecla in source, f"o harness não envia {tecla} real"
    assert "mouseClick(" in source, "abrir, examinar e importar têm de sair do mouse real"
    assert "esdeImportDialog.moveVertical(" not in source, (
        "chamar moveVertical diretamente é teste complementar, não prova do input"
    )
    assert "revealEsdeImportItem(" not in source, (
        "o harness não pode revelar o foco pela mão para provar a rolagem"
    )
    assert "closeIfOpen()" in source, (
        "close() continua sendo só a limpeza controlada; a prova é a tecla real"
    )


def test_o_harness_espera_estabilizacao_com_limite_e_falha() -> None:
    """Nada de ``sleep`` fixo: espera observável, com budget e falha nomeada."""
    source = _harness_source()
    assert "function waitFor(" in source, "falta o polling com limite de tempo"
    assert "function settleLayout(" in source, "falta a espera de estabilização do layout"
    assert "expirou o limite" in source, "estourar o limite precisa falhar de forma explícita"
    assert "ESTABILIZOU" in source, "a estabilização tem de ser reportada com o tempo medido"


def test_o_cenario_extenso_nao_pode_ser_vazio() -> None:
    """O cenário que exercita rolagem tem de provar que o conteúdo passa da banda,
    e o alcance por tecla real tem de partir de outro controle — chegar ao primary
    com 0 pressões porque o clique anterior já o deixou focado não prova nada."""
    source = _harness_source()
    assert "pressoesAtePrimary" in source, "o número de pressões até o primary tem de ser medido"
    assert "0 pressões significa que o clique anterior deixou o " in source, (
        "falta a guarda explícita contra descida vacua ate o primary"
    )


def test_a_captura_de_evidencia_existe_e_usa_dados_locais() -> None:
    assert CAPTURE.is_file(), f"{CAPTURE} não existe"
    source = CAPTURE.read_text(encoding="utf-8")
    assert "Window {" in source, "a captura carrega o painel numa Window real"
    assert "--output-dir=" in source and "--label=" in source, (
        "a captura precisa aceitar pasta e rótulo para registrar antes/depois"
    )
    assert "TIMEOUT" in source, "captura sem limite de tempo pode travar o gate"
    assert "harness.phase = 500\n        harness.contentItem.grabToImage" in source, (
        "grabToImage é assíncrono: sem tomar a fase antes do grab o Timer reentra "
        "na mesma fase e emite capturas fora da lista (medido: rc=1 com mais "
        "capturas que nomes; ver o log 04 da pasta de evidência)"
    )
    for texto in ("theme.import.esde.inspect", "theme.import.esde.apply"):
        assert texto in source, f"a captura não exercita {texto}"


@pytest.mark.visual
def test_dialogo_esde_fica_alcancavel_em_qualquer_viewport() -> None:
    """Os 11 cenários de contrato, executados pelo Qt 6 do ambiente."""
    assert RUNNER is not None, "qmltestrunner Qt 6 é obrigatório para esta prova"
    completed = subprocess.run(
        [str(RUNNER), "-input", str(HARNESS)],
        cwd=ROOT,
        env=_environment(),
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    assert completed.returncode == 0, f"harness de viewport reprovou:\n{output[-4000:]}"
    assert "FAIL" not in output, f"cenário de viewport reprovou:\n{output[-4000:]}"
    assert "Totals: 13 passed, 0 failed" in output, (
        "a suíte de viewport não rodou inteira:\n" + output[-4000:]
    )


@pytest.mark.visual
def test_capturas_de_evidencia_dos_dois_viewports(tmp_path: Path) -> None:
    """Renderiza as cinco telas do lote e confere a geometria de cada PNG."""
    assert QML is not None, "binário qml Qt 6 é obrigatório para a captura"
    destination = tmp_path / "esde-import-viewport"
    destination.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [str(QML), str(CAPTURE), "--", f"--output-dir={destination}", "--label=gate"],
        cwd=ROOT,
        env=_environment(),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    assert completed.returncode == 0, f"captura de evidência falhou:\n{output[-3000:]}"
    assert "undefined-" not in output, (
        "a captura escreveu fora da lista de nomes — fase reentrada:\n" + output[-1500:]
    )
    from PIL import Image

    esperado = {
        "1-compacto-acoes-e-corpo": (949, 593),
        "2-compacto-listagem-24-esquemas": (949, 593),
        "3-compacto-rodape-fixo-com-campo-de-nome-focado": (949, 593),
        "4-compacto-relatorio-extenso": (949, 593),
        "5-largo-relatorio-extenso": (1280, 800),
    }
    for nome in CAPTURE_NAMES:
        arquivo = destination / f"{nome}-gate.png"
        assert arquivo.is_file(), f"faltou a captura {nome}:\n{output[-1500:]}"
        with Image.open(arquivo) as imagem:
            assert imagem.size == esperado[nome], f"{nome} saiu com {imagem.size}"
        assert arquivo.stat().st_size > 20_000, f"{nome} é uma tela quase vazia"
