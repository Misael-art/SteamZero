# SPDX-License-Identifier: GPL-3.0-or-later
"""Sonda de mordida do contrato de captura — autocontida, reexecutável da raiz do repositório.

    .venv/bin/python docs/09-operations/evidence/2026-09-27-gate-visual-causa-e-contrato/05-sonda-de-mordida.py

Cada caso abaixo é uma imagem que **passaria** no proxy antigo (`st_size > 20_000`) ou
que ele classificava mal, e que o contrato atual trata de um jeito verificável. Os
arquivos usados são os versionados neste repositório: a baseline da cena e a captura
real que o runner do CI produzia sem nenhuma fonte (`imagens/01-…`). A saída literal
desta sonda é `04-sonda-de-mordida-do-contrato.txt`.

Não é um teste pytest de propósito: ele serve para *ler* o comportamento das três
verificações, inclusive as que a suíte já assenta. As asserções de mordida que a
suíte garante estão em `test_o_contrato_de_captura_reprova_vazio_ausente_e_corte`.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests" / "integration"))

from qml_capture_runner import CaptureError, assert_not_empty, compare_with_golden  # noqa: E402
from test_esde_import_dialog_compact import BACKGROUND, GOLDEN_DIR, _dentro_da_banda  # noqa: E402

CENA = "1-compacto-acoes-e-corpo"
SEM_FONTE = HERE / "imagens" / "01-cena-1-no-container-sem-fonte.png"


def caso(rotulo: str, arquivo: Path, golden: Path, work: Path, moldura: tuple[int, int]) -> None:
    print(f"\n--- {rotulo}: {arquivo.name} ({arquivo.stat().st_size} bytes)")
    print("    decodifica e tem o viewport pedido:", Image.open(arquivo).size == moldura)
    try:
        assert_not_empty(arquivo, background=BACKGROUND)
        print("    assert_not_empty .............. passa")
    except CaptureError as exc:
        print(f"    assert_not_empty .............. REPROVA -> {exc}")
    try:
        metrics = compare_with_golden(arquivo, golden, work / arquivo.stem)
        veredito = "passa" if metrics.changed_pixel_count == 0 else "REPROVA"
        print(
            f"    compare_with_golden ........... {veredito} "
            f"(changed={metrics.changed_pixel_count}/{moldura[0] * moldura[1]}, "
            f"ratio={metrics.changed_pixel_ratio:.4f}, "
            f"maxDelta={metrics.maximum_channel_delta}, bbox={metrics.bounding_box_of_changes})"
        )
    except CaptureError as exc:
        print(f"    compare_with_golden ........... REPROVA -> {exc}")
    print(f"    proxy antigo (> 20 000 bytes) ... {'passa' if arquivo.stat().st_size > 20_000 else 'reprova'}")


def main() -> int:
    golden = GOLDEN_DIR / f"{CENA}.png"
    moldura = Image.open(golden).size
    print(f"baseline {golden.relative_to(ROOT)}: viewport {moldura}, {golden.stat().st_size} bytes")
    assert SEM_FONTE.is_file(), f"falta a captura do runner em {SEM_FONTE}"
    with tempfile.TemporaryDirectory(prefix="sz-sonda-") as bruto:
        work = Path(bruto)

        em_branco = work / "uniforme-fundo.png"
        Image.new("RGBA", moldura, BACKGROUND).save(em_branco)
        caso("captura vazia (fundo uniforme, viewport correto)", em_branco, golden, work, moldura)

        runner = work / "runner-sem-fonte.png"
        shutil.copyfile(SEM_FONTE, runner)
        caso("a captura real do runner que reprovou o CI", runner, golden, work, moldura)

        um_pixel = work / "um-pixel.png"
        imagem = Image.open(golden).convert("RGBA")
        imagem.putpixel((400, 300), (255, 0, 255, 255))
        imagem.save(um_pixel)
        caso("golden com exatamente um pixel trocado", um_pixel, golden, work, moldura)

        caso("golden correto (deve passar)", golden, golden, work, moldura)

        print("\n--- corte de regime, decidido pela geografia declarada pela cena")
        for ret, quadro, rotulo in [
            ((493, 1041, 141, 48), moldura, "acao ES-DE compacto ANTES da 3a fatia"),
            ((663, 529, 132, 48), moldura, "acao ES-DE compacto DEPOIS"),
            ((828, 632, 132, 48), (1280, 800), "acao ES-DE no viewport largo"),
            ((828, 632, 132, 48), moldura, "a mesma acao larga, na moldura compacta"),
        ]:
            print(
                f"    {rotulo}: ret {ret} contra moldura {quadro} -> "
                f"{'dentro' if _dentro_da_banda(ret, quadro) else 'FORA'}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
