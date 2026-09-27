# SPDX-License-Identifier: GPL-3.0-or-later
"""UX-05/UX-07 — o diálogo "Importar cena RetroFE" em viewport compacto.

Seis testes em quatro papéis:

* As três guardas de intenção rodam **sempre**, inclusive onde não há Qt. São a
  guarda contra "consertar" a reprovação trocando o evento real por chamada de
  volta, por atraso fixo ou por rolagem manual: contrato de viewport só vale se
  medido com teclado/click reais, espera observável com limite e falha, e
  captura que existe e só usa dados locais.
* ``test_dialogo_retrofe_fica_alcancavel_em_qualquer_viewport`` (``visual``)
  executa o harness QtTest com ``qmltestrunner`` no runtime do projeto e reprova
  se qualquer um dos 11 cenários falhar.
* ``test_capturas_de_evidencia_dos_dois_viewports`` (``visual``) roda a cena de
  captura para o diretório temporário do pytest — fora do checkout — e confere a
  imagem contra a baseline versionada da cena, no viewport que a própria cena
  declarou, com as ações dentro da moldura. A leitura das imagens é humana, na
  pasta de evidência; nada aqui afirma que a release instalada no host foi
  testada.
* ``test_o_contrato_de_captura_reprova_vazio_ausente_e_corte`` roda sem Qt e é a
  prova de que o contrato de captura acima não é decorativo: captura vazia,
  conteúdo ausente, corte de rodapé e cena muda (sem geografia declarada) têm de
  reprovar. É o substituto honesto do ``st_size > 20_000`` que existia aqui.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from qml_capture_runner import (  # noqa: E402
    CanonicalEnvironment,
    CaptureError,
    assert_not_empty,
    compare_with_golden,
)

HARNESS = ROOT / "tests" / "qml" / "check_retrofe_import_dialog_compact_viewport.qml"
CAPTURE = ROOT / "tests" / "qml" / "capture_retrofe_import_viewport.qml"

#: Baseline de cada uma das quatro cenas, gerada no ambiente canônico do gate
#: visual (fonte empacotada isolada, Qt 6.11.2, software, DPI 96, locale fixo).
GOLDEN_DIR = ROOT / "tests" / "qml" / "golden" / "import-dialogs" / "retrofe"

#: Para onde a captura vai ANTES de qualquer asserção. O `tmp_path` do pytest
#: nasce dentro do `TMPDIR` que `run_tests_isolated.py` realoca e apaga ao sair,
#: então publicar dali é publicar nada: foi assim que o gate visual ficou
#: vermelho no CI três vezes seguidas sem nenhuma imagem anexada.
EVIDENCE_DIR = ROOT / "build" / "visual-evidence" / "retrofe-import"

#: Cor de fundo declarada pela cena (`capture_retrofe_import_viewport.qml`).
BACKGROUND = "#071019"

CAPTURE_NAMES = (
    "1-compacto-acoes-e-corpo",
    "2-compacto-foco-rola-destino",
    "3-compacto-relatorio-extenso",
    "4-largo-relatorio-extenso",
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
    """Ambiente canônico do gate visual, declarado — não herdado do host.

    No host a omissão passava despercebida porque existem 828 fontes no
    fontconfig; na imagem do gate não existe nenhuma, e o Qt desenha cada glifo
    como caixa de tofu — geometria certa, texto ausente. É o mesmo ambiente que
    produz as dez baselines versionadas, inclusive a fonte empacotada isolada.
    """
    return CanonicalEnvironment().to_env()


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
    assert "mouseClick(" in source, "abrir, examinar e publicar têm de sair do mouse real"
    assert "retrofeImportDialog.moveVertical(" not in source, (
        "chamar moveVertical diretamente é teste complementar, não prova do input"
    )
    assert "revealRetrofeImportItem(" not in source, (
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


def test_a_captura_de_evidencia_existe_e_usa_dados_locais() -> None:
    assert CAPTURE.is_file(), f"{CAPTURE} não existe"
    source = CAPTURE.read_text(encoding="utf-8")
    assert "Window {" in source, "a captura carrega o painel numa Window real"
    assert "--output-dir=" in source and "--label=" in source, (
        "a captura precisa aceitar pasta e rótulo para registrar antes/depois"
    )
    assert "TIMEOUT" in source, "captura sem limite de tempo pode travar o gate"
    assert "harness.phase = 500\n        harness.contentItem.grabToImage" in source, (
        "grabToImage é assíncrono: sem tomar a fase antes do grab o Timer reentra na "
        "mesma fase e emite capturas fora da lista (medido sob carga: 'capturas=5 de "
        "4' com undefined-gate.png e rc=1, intercalado com 4 de 4)"
    )
    for texto in ("theme.import.retrofe.inspect", "theme.import.retrofe.apply"):
        assert texto in source, f"a captura não exercita {texto}"


@pytest.mark.visual
def test_dialogo_retrofe_fica_alcancavel_em_qualquer_viewport() -> None:
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


def _rectos(valor: str) -> tuple[int, int, int, int]:
    esquerda, topo, largura, altura = (int(campo) for campo in valor.split(","))
    return esquerda, topo, largura, altura


def _geometria(output: str) -> dict[str, dict[str, object]]:
    """Lê o que a cena declarou sobre si mesma, linha `GEOMETRIA|` por captura.

    Sem isso a imagem só provaria dimensão. Com ela, o retângulo do botão vem da
    árvore viva no instante do `grabToImage`, e "a linha de ações saiu da moldura"
    deixa de ser uma frase sobre um PNG para virar uma desigualdade verificável.
    """
    cenas: dict[str, dict[str, object]] = {}
    for linha in output.splitlines():
        if "GEOMETRIA|" not in linha:
            continue
        campos = linha.split("GEOMETRIA|", 1)[1].split("|")
        cena: dict[str, object] = {"janela": None}
        for campo in campos[1:]:
            chave, _, valor = campo.partition("=")
            if chave == "janela":
                largura, _, altura = valor.partition("x")
                cena["janela"] = (int(largura), int(altura))
            else:
                cena[chave] = _rectos(valor)
        cenas[campos[0]] = cena
    return cenas


def _dentro_da_banda(ret: tuple[int, int, int, int], moldura: tuple[int, int]) -> bool:
    esquerda, topo, largura, altura = ret
    return (
        esquerda >= 0
        and topo >= 0
        and esquerda + largura <= moldura[0]
        and topo + altura <= moldura[1]
    )


def _publicar(
    destination: Path,
    tmp_path: Path,
    output: str,
    cenas: dict[str, dict[str, object]],
) -> None:
    """Escreve a captura e o que a cerca ANTES de qualquer asserção.

    Os caminhos do host são substituídos pelo marcador `<tmp>` antes de o log ser
    copiado — o artefato não publica diretório de usuário nem árvore de trabalho.
    """
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    for arquivo in sorted(destination.glob("*.png")):
        shutil.copyfile(arquivo, EVIDENCE_DIR / arquivo.name)
    (EVIDENCE_DIR / "geometria.json").write_text(
        json.dumps(cenas, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (EVIDENCE_DIR / "ambiente.json").write_text(
        json.dumps(CanonicalEnvironment().to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (EVIDENCE_DIR / "saida-do-runner.txt").write_text(
        output.replace(str(tmp_path), "<tmp>"), encoding="utf-8"
    )


@pytest.mark.visual
def test_capturas_de_evidencia_dos_dois_viewports(tmp_path: Path) -> None:
    """Renderiza as quatro telas do lote e confere cada PNG contra a baseline."""
    assert QML is not None, "binário qml Qt 6 é obrigatório para a captura"
    destination = tmp_path / "retrofe-import-viewport"
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
    cenas = _geometria(output)
    _publicar(destination, tmp_path, output, cenas)
    from PIL import Image

    esperado = {
        "1-compacto-acoes-e-corpo": (949, 593),
        "2-compacto-foco-rola-destino": (949, 593),
        "3-compacto-relatorio-extenso": (949, 593),
        "4-largo-relatorio-extenso": (1280, 800),
    }
    assert completed.returncode == 0, f"captura de evidência falhou:\n{output[-3000:]}"
    assert "undefined-" not in output, (
        "a captura escreveu fora da lista de nomes — fase reentrada:\n" + output[-1500:]
    )
    for nome in CAPTURE_NAMES:
        arquivo = destination / f"{nome}-gate.png"
        assert arquivo.is_file(), f"faltou a captura {nome}:\n{output[-1500:]}"
        cena = cenas.get(nome)
        assert cena is not None, f"a cena {nome} não publicou a linha GEOMETRIA:\n{output[-1500:]}"
        with Image.open(arquivo) as imagem:
            assert imagem.size == esperado[nome], f"{nome} saiu com {imagem.size}"
        # O viewport que a cena diz ter renderizado tem de ser o pedido: as duas
        # fontes (o `Qt.size` do grab e o retângulo declarado) precisam concordar.
        assert cena["janela"] == esperado[nome], (
            f"{nome} declarou janela {cena['janela']} e entregou {esperado[nome]}"
        )
        assert_not_empty(arquivo, background=BACKGROUND)
        moldura = esperado[nome]
        for chave in ("rodape", "acao"):
            ret = cena[chave]
            assert isinstance(ret, tuple), f"{nome}: sem retângulo de {chave}"
            assert _dentro_da_banda(ret, moldura), (
                f"{nome}: {chave} em {ret} está fora da moldura {moldura} — "
                "é exatamente o corte que a segunda fatia corrigiu"
            )
        metrics = compare_with_golden(arquivo, GOLDEN_DIR / f"{nome}.png", EVIDENCE_DIR / nome)
        assert metrics.changed_pixel_count == 0, (
            f"{nome} divergiu da baseline em {metrics.changed_pixel_count} pixels "
            f"(máximo delta de canal {metrics.maximum_channel_delta}, "
            f"bounding box {metrics.bounding_box_of_changes}); "
            f"diff/overlay em {EVIDENCE_DIR / nome}"
        )


def test_o_contrato_de_captura_reprova_vazio_ausente_e_corte(tmp_path: Path) -> None:
    """Os modos de falha que o gate precisa pegar, provados sem Qt.

    Espelho do gate ES-DE: trocar o limiar de bytes por baseline + geografia só
    vale se a prova nova for mais forte, não mais cômoda. Cada caso é uma imagem
    que passaria no proxy antigo e reprova no contrato atual.
    """
    from PIL import Image

    nome = "1-compacto-acoes-e-corpo"
    golden = GOLDEN_DIR / f"{nome}.png"
    moldura = Image.open(golden).size
    assert moldura == (949, 593), f"a baseline saiu do viewport medido: {moldura}"

    # 1) Captura vazia: a moldura inteira na cor de fundo. Tamanho certo, e
    #    bytes suficientes para enganar qualquer limiar de tamanho.
    em_branco = tmp_path / "em-branco.png"
    Image.new("RGBA", moldura, (7, 16, 25, 255)).save(em_branco)
    with pytest.raises(CaptureError):
        assert_not_empty(em_branco, background=BACKGROUND)

    # 2) Conteúdo ausente: um pixel que falte já reprova.
    desviada = tmp_path / "desviada.png"
    imagem = Image.open(golden).convert("RGBA")
    imagem.putpixel((10, 10), (255, 0, 255, 255))
    imagem.save(desviada)
    assert compare_with_golden(desviada, golden, tmp_path / "diff").changed_pixel_count == 1

    # 3) Corte relevante: com o relatório de erro extenso na árvore ANTES da
    #    correção, "Publicar cena" descia a y=1210 numa janela de 593.
    assert not _dentro_da_banda((742, 1210, 83, 44), moldura)
    assert _dentro_da_banda((742, 537, 83, 44), moldura)

    # 4) Cena que não declara a própria geografia não tem como ser aprovada.
    assert _geometria("debug|CAPTURADO <tmp>/1-compacto-acoes-e-corpo-gate.png") == {}
    declarada = _geometria(
        "debug|GEOMETRIA|1-compacto-acoes-e-corpo|janela=949x593"
        "|dialogo=125,12,700,569|corpo=131,44,688,487|rodape=125,537,700,44"
        "|acao=742,537,83,44"
    )
    cena = declarada[nome]
    assert cena["janela"] == (949, 593)
    assert cena["acao"] == (742, 537, 83, 44)
