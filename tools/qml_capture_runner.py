# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-03 — harness de captura QML pertencente ao projeto.

Os dez harnesses legados são o teste: cada `check_*.qml` faz suas próprias
asserções e chama `Qt.exit(0)`. Isso tem dois furos que já custaram caro aqui.

O primeiro é o `skip`: quando o Qt falta, a suíte fica verde num host onde nada
visual foi verificado. Foi assim que a regressão de ícones da a37 atravessou os
gates. O segundo é mais sutil — este host tem ``QT_LOGGING_RULES=*=false``, que
silencia TODO log do Qt. Um harness que herdasse o ambiente do desenvolvedor
verificaria a ausência de warnings numa sessão onde warning nenhum consegue ser
emitido.

Por isso o runner não herda ambiente: ele monta o ambiente canônico do zero e
remove qualquer ``QT_*``/``QML_*`` herdado. Reprodutibilidade byte a byte entre
duas máquinas depende disso.

Aqui a autoridade é Python. O QML é cenário; quem decide aprovação é este
módulo, olhando artefatos: imagem, geometria, warnings, ambiente.

**Escolha de runtime.** O produto lança o próprio binário ``qml6`` como
subprocesso (``desktop_ui.launch_desktop_ui``). Não usa PySide6 nem Qt/C++
próprio. Como o harness deve acompanhar o runtime do produto, ele dirige o mesmo
``qml6`` — e o que muda em relação ao legado não é o binário, é quem manda: o
runner controla ambiente, canvas, DPI, locale, fontes, espera, captura e
veredito. Introduzir PySide6 só para teste criaria um segundo runtime Qt no
projeto, e passaria a validar uma pilha que o usuário nunca executa.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

#: Ambiente ausente ou inutilizável. O código genérico; os demais dizem o quê.
DIAG_ENVIRONMENT = "QML-VISUAL-ENVIRONMENT-001"
DIAG_QT_VERSION = "QML-VISUAL-QT-VERSION-002"
DIAG_PLUGIN = "QML-VISUAL-PLUGIN-003"
DIAG_FONT = "QML-VISUAL-FONT-004"
DIAG_CAPTURE = "QML-VISUAL-CAPTURE-005"
DIAG_EMPTY_IMAGE = "QML-VISUAL-EMPTY-IMAGE-006"
DIAG_WARNING = "QML-VISUAL-WARNING-007"
DIAG_GOLDEN_MISSING = "QML-VISUAL-GOLDEN-MISSING-008"

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tools" / "qml_capture" / "CaptureHarness.qml"

#: Versão mínima do Qt. Abaixo disto o comportamento de `grabToImage` sob o
#: backend software difere, e um golden gerado numa versão não vale na outra.
MINIMUM_QT = (6, 5)

#: Warnings que reprovam. `Unable to assign` é o que apareceria se o adapter
#: emitisse um valor que o QML não aceita — o defeito que o VS-02 previne, e que
#: precisa reprovar aqui caso escape.
FORBIDDEN_WARNINGS = (
    "Binding loop",
    "Unable to assign",
    "TypeError:",
    "ReferenceError:",
    "Cannot open:",
    "is not a type",
    "Cannot assign",
    "File not found",
)

#: Mensagens que o Qt REALMENTE emite quando o plugin de plataforma falta.
#: Copiadas de uma execução, não escritas de memória: a primeira versão desta
#: checagem procurava um texto que o Qt nunca emite, e nunca disparava.
PLUGIN_FAILURE_MARKERS = (
    "Could not find the Qt platform plugin",
    "no Qt platform plugin could be initialized",
)

_QT_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
_MESSAGE = re.compile(r"^(?P<type>debug|info|warning|critical|fatal)\|(?P<text>.*)$")


class Backend(StrEnum):
    """Backend de renderização do scene graph.

    ``SOFTWARE`` é o canônico: determinístico, sem GPU, mesmo resultado em
    qualquer runner. ``RHI`` fica reservado para o que o software não desenha —
    máscaras compostas, blur, shaders —, e é categoria separada de propósito
    (ver ``visual-rhi`` no P0-08). Um golden de um não vale para o outro.
    """

    SOFTWARE = "software"
    RHI = "rhi"


class CaptureError(RuntimeError):
    """Falha com código de diagnóstico. Nunca degrada para `skip`."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CanonicalEnvironment:
    """O ambiente que o cenário exige, declarado por extenso.

    Cada campo aqui é uma variável que, se herdada do host, mudaria o pixel
    produzido. Fixar todos é o que permite comparar a captura de hoje com um
    golden gerado noutra máquina.
    """

    platform: str = "offscreen"
    backend: Backend = Backend.SOFTWARE
    device_pixel_ratio: float = 1.0
    font_dpi: int = 96
    locale: str = "C.UTF-8"
    scale_factor: float = 1.0
    animations: bool = False
    #: Perfil de acessibilidade. Entra no ambiente porque altera o render.
    reduced_motion: bool = True
    high_contrast: bool = False

    def to_env(self) -> dict[str, str]:
        """Ambiente COMPLETO, montado do zero.

        Não parte de ``os.environ``: este host tem ``QT_LOGGING_RULES=*=false``,
        e herdá-lo faria a coleta de warnings verificar o silêncio de um Qt
        amordaçado. O mesmo vale para ``QT_MESSAGE_PATTERN``, que muda o formato
        que este módulo analisa.
        """
        preserved = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith(("QT_", "QML_", "QSG_", "LC_", "LANG"))
        }
        preserved.update(
            {
                "QT_QPA_PLATFORM": self.platform,
                "QT_QUICK_BACKEND": self.backend.value,
                "QT_FORCE_STDERR_LOGGING": "1",
                # Vazio, não ausente: ausente deixaria a regra do host valer.
                "QT_LOGGING_RULES": "",
                # `%{type}` é o que torna warning distinguível de info. Sem ele
                # tudo sai como "qml: ", e a coleta não conseguiria classificar.
                "QT_MESSAGE_PATTERN": "%{type}|%{message}",
                "QT_SCALE_FACTOR": str(self.scale_factor),
                "QT_FONT_DPI": str(self.font_dpi),
                "QT_ENABLE_HIGHDPI_SCALING": "0",
                "QT_SCREEN_SCALE_FACTORS": str(self.device_pixel_ratio),
                "QML_DISABLE_DISK_CACHE": "1",
                "LC_ALL": self.locale,
                "LANG": self.locale,
            }
        )
        return preserved

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "backend": self.backend.value,
            "devicePixelRatio": self.device_pixel_ratio,
            "fontDpi": self.font_dpi,
            "locale": self.locale,
            "scaleFactor": self.scale_factor,
            "animations": self.animations,
            "reducedMotion": self.reduced_motion,
            "highContrast": self.high_contrast,
        }


@dataclass(frozen=True)
class QmlMessage:
    """Uma linha de log do Qt, já classificada."""

    level: str
    text: str

    @property
    def forbidden(self) -> bool:
        return any(marker in self.text for marker in FORBIDDEN_WARNINGS)


@dataclass
class CaptureResult:
    """O que a execução produziu, para o teste julgar."""

    image: Path
    geometry: dict[str, Any]
    messages: tuple[QmlMessage, ...]
    environment: dict[str, Any]
    exit_code: int
    stderr: str
    artifacts: dict[str, Path] = field(default_factory=dict)

    @property
    def forbidden_messages(self) -> tuple[QmlMessage, ...]:
        return tuple(item for item in self.messages if item.forbidden)


def find_runtime() -> Path:
    """Localiza o ``qml6``, ou reprova.

    Nunca devolve ``None`` para o chamador decidir pular. Ambiente ausente é
    falha explícita — é a regra que separa este harness dos dez legados.
    """
    found = shutil.which("qml6") or shutil.which("qml")
    if found is None:
        raise CaptureError(
            DIAG_ENVIRONMENT,
            "runtime QML ausente (qml6). O contrato entre o adapter e "
            "SceneText.qml não pode ser verificado sem ele, e declarar verde "
            "sem verificar é o que deixou a regressão de ícones passar.",
        )
    return Path(found)


def check_runtime_version(runtime: Path) -> tuple[int, ...]:
    """Confere a versão do Qt. Golden gerado noutra versão não vale."""
    try:
        completed = subprocess.run(
            [str(runtime), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CaptureError(DIAG_QT_VERSION, f"não foi possível consultar a versão: {exc}") from exc

    match = _QT_VERSION.search(completed.stdout + completed.stderr)
    if match is None:
        raise CaptureError(
            DIAG_QT_VERSION,
            f"versão do Qt não identificada em {completed.stdout!r} {completed.stderr!r}",
        )
    version = tuple(int(part) for part in match.groups() if part is not None)
    if version[:2] < MINIMUM_QT:
        raise CaptureError(
            DIAG_QT_VERSION,
            f"Qt {'.'.join(str(part) for part in version)} abaixo do mínimo "
            f"{'.'.join(str(part) for part in MINIMUM_QT)}",
        )
    return version


def parse_messages(stderr: str) -> tuple[QmlMessage, ...]:
    """Classifica o stderr do Qt.

    Depende de ``QT_MESSAGE_PATTERN`` estar como o ambiente canônico define. Uma
    linha que não casa vira ``warning``: não classificar é perder informação, e
    perder informação num coletor de warnings anula o coletor.
    """
    messages: list[QmlMessage] = []
    for line in stderr.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _MESSAGE.match(stripped)
        if match is None:
            messages.append(QmlMessage(level="warning", text=stripped))
            continue
        messages.append(QmlMessage(level=match.group("type"), text=match.group("text")))
    return tuple(messages)


def font_fingerprint(family: str) -> dict[str, str]:
    """Arquivo e hash da fonte que o sistema resolve para ``family``.

    Vai para ``environment.json`` porque duas distribuições empacotam versões
    diferentes da MESMA família, e o texto sai com métrica diferente. Sem o
    hash, uma divergência de golden causada por atualização de pacote de fonte
    pareceria regressão de código.
    """
    record: dict[str, str] = {"family": family}
    matcher = shutil.which("fc-match")
    if matcher is None:
        record["file"] = "fc-match indisponível"
        return record
    version = shutil.which("fc-list")
    if version is not None:
        record["fontconfig"] = "presente"
    try:
        completed = subprocess.run(
            [matcher, "--format=%{file}", family],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        record["file"] = "fc-match falhou"
        return record
    path = Path(completed.stdout.strip())
    # O caminho FÍSICO aparece aqui, e só aqui. `environment.json` é artefato
    # interno de diagnóstico do harness; o IR e o modelo entregue ao tema
    # continuam recebendo apenas o handle opaco.
    record["file"] = str(path)
    record["logicalPath"] = f"asset://font/{path.stem}"
    if path.is_file():
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        record["bytes"] = str(path.stat().st_size)
    return record


def _extract(messages: Sequence[QmlMessage], prefix: str) -> str | None:
    for item in messages:
        if item.text.startswith(prefix):
            return item.text[len(prefix) :].strip()
    return None


def _reject_pending_payload(model: Mapping[str, Any]) -> None:
    """Defesa em profundidade na fronteira do harness.

    O adapter já impede que um resultado `failed` vire payload, e
    `require_model()` é a única porta. Mas nada impede alguém de montar o
    dicionário à mão — e foi o que revelou o furo: um `{"text": {"bind": ...}}`
    passado direto renderizou "[object Object]" sem erro nenhum, porque o QML
    aceita objeto onde espera string.

    A validação aqui não substitui o adapter. Ela garante que a ÚNICA forma de
    chegar ao QML seja com valores já resolvidos, independentemente de quem
    chamou.
    """
    from steamzero.domain.scene_value import is_pending_value

    def walk(node: Any, where: str) -> None:
        if isinstance(node, dict):
            if is_pending_value(node):
                raise CaptureError(
                    DIAG_CAPTURE,
                    f"valor não resolvido em {where}: {node!r}. O QML renderizaria "
                    "'[object Object]' sem reclamar.",
                )
            for key, item in node.items():
                walk(item, f"{where}.{key}")
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{where}[{index}]")

    walk(dict(model), "model")


def capture(
    model: Mapping[str, Any],
    *,
    output: Path,
    canvas: tuple[int, int] = (1920, 1080),
    background: str = "#000000",
    environment: CanonicalEnvironment | None = None,
    timeout: float = 60.0,
) -> CaptureResult:
    """Renderiza um ``QmlTextRenderModel`` e devolve o que foi produzido.

    ``model`` é o payload de ``QmlTextRenderModel.to_dict()`` — já resolvido,
    já traduzido. O harness não tem acesso a registry nenhum, e não teria como
    ter: o que atravessa é um dicionário de escalares.
    """
    _reject_pending_payload(model)
    env_spec = environment or CanonicalEnvironment()
    # RHI sob `offscreen` não tem GPU para inicializar e simplesmente NÃO
    # retorna — verificado, consome o timeout inteiro e reporta "layout não
    # estabilizou", que manda quem investiga para o lugar errado. Recusar a
    # combinação aqui custa nada e diz a verdade.
    if env_spec.backend is Backend.RHI and env_spec.platform == "offscreen":
        raise CaptureError(
            DIAG_PLUGIN,
            "backend rhi não inicializa sob a plataforma offscreen; "
            "o gate `visual-rhi` é categoria separada e ainda não existe (P0-08)",
        )
    runtime = find_runtime()
    version = check_runtime_version(runtime)

    output.mkdir(parents=True, exist_ok=True)
    image = output / "actual.png"
    image.unlink(missing_ok=True)

    config = {
        "model": dict(model),
        "canvasWidth": canvas[0],
        "canvasHeight": canvas[1],
        "background": background,
        "imagePath": str(image),
    }

    try:
        completed = subprocess.run(
            [
                str(runtime),
                str(HARNESS),
                "--",
                "--config-json",
                json.dumps(config, ensure_ascii=False),
            ],
            cwd=ROOT,
            env=env_spec.to_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # Timeout não é "demorou": é layout que não estabilizou. O estado
        # coletado até aqui é o que permite descobrir por quê.
        stderr = exc.stderr or b""
        raise CaptureError(
            DIAG_CAPTURE,
            f"layout não estabilizou em {timeout}s; stderr:\n"
            f"{stderr.decode(errors='replace') if isinstance(stderr, bytes) else stderr}",
        ) from exc

    messages = parse_messages(completed.stderr)

    if any(marker in completed.stderr for marker in PLUGIN_FAILURE_MARKERS):
        raise CaptureError(
            DIAG_PLUGIN,
            f"plugin de plataforma {env_spec.platform!r} indisponível; stderr:\n{completed.stderr}",
        )

    failure = _extract(messages, "HARNESS-FAIL ")
    if failure is not None:
        code, _, detail = failure.partition(" ")
        raise CaptureError(code or DIAG_CAPTURE, detail)

    if completed.returncode != 0:
        raise CaptureError(
            DIAG_CAPTURE,
            f"harness saiu com {completed.returncode}; stderr:\n{completed.stderr}",
        )

    if not image.exists():
        raise CaptureError(DIAG_CAPTURE, f"captura não produziu {image}")

    raw_geometry = _extract(messages, "HARNESS-GEOMETRY ")
    if raw_geometry is None:
        raise CaptureError(DIAG_CAPTURE, "harness não publicou o relatório geométrico")
    geometry = json.loads(raw_geometry)

    env_record = {
        **env_spec.to_dict(),
        "qtRuntime": str(runtime),
        "qtVersion": ".".join(str(part) for part in version),
        "fontFamilyRequested": geometry.get("fontFamilyRequested", ""),
        "fontFamilyResolved": geometry.get("fontFamilyResolved", ""),
        "fontFile": font_fingerprint(str(geometry.get("fontFamilyRequested", ""))),
        "requestedFontFamily": geometry.get("fontFamilyRequested", ""),
        "availableFontFamilyCount": geometry.get("availableFontFamilyCount", 0),
        "testFontAvailable": geometry.get("testFontAvailable", False),
        "fallbackDetected": geometry.get("fallbackDetected", False),
        "canvas": {"width": canvas[0], "height": canvas[1]},
    }

    return CaptureResult(
        image=image,
        geometry=geometry,
        messages=messages,
        environment=env_record,
        exit_code=completed.returncode,
        stderr=completed.stderr,
    )


def write_artifacts(
    result: CaptureResult,
    output: Path,
    *,
    resolved_node: Mapping[str, Any] | None = None,
    adaptation: Mapping[str, Any] | None = None,
    translation_log: Mapping[str, Any] | None = None,
) -> dict[str, Path]:
    """Publica o que a execução produziu.

    Em falha estes arquivos são a única forma de descobrir o que aconteceu numa
    máquina que não é a sua — por isso são escritos sempre, não só no sucesso.
    """
    output.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {"actual.png": result.image}

    documents: dict[str, Any] = {
        "qml-render-model.json": result.geometry,
        "environment.json": result.environment,
    }
    if resolved_node is not None:
        documents["resolved-node.json"] = dict(resolved_node)
    if adaptation is not None:
        documents["adaptation-result.json"] = dict(adaptation)
    if translation_log is not None:
        documents["translation-log.json"] = dict(translation_log)

    for name, payload in documents.items():
        path = output / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        written[name] = path

    warnings = output / "qml-warnings.txt"
    warnings.write_text(
        "\n".join(f"{item.level}|{item.text}" for item in result.messages),
        encoding="utf-8",
    )
    written["qml-warnings.txt"] = warnings

    result.artifacts = written
    return written


def _load(path: Path) -> Any:
    """Importa Pillow tarde, e reprova com código próprio se faltar."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - o lock de dev traz Pillow
        raise CaptureError(
            DIAG_ENVIRONMENT, "Pillow ausente; sem ele não há como validar a captura"
        ) from exc
    return Image.open(path).convert("RGBA")


def assert_not_empty(image: Path, *, background: str = "#000000") -> int:
    """Imagem uniforme é imagem vazia, mesmo com o tamanho certo.

    A checagem no QML só pega dimensão zero. Uma captura de 1920x1080 inteira na
    cor de fundo passa por ela — e é exatamente o que sai quando o componente não
    carregou, quando o texto ficou fora do canvas ou quando a cor foi resolvida
    igual ao fundo. Sem esta verificação, o golden congelaria uma tela em branco.
    """
    picture = _load(image)
    colours = picture.getcolors(maxcolors=picture.width * picture.height)
    if colours is None or len(colours) <= 1:
        raise CaptureError(
            DIAG_EMPTY_IMAGE,
            f"{image} tem uma cor só; o componente não desenhou nada sobre o fundo",
        )
    return len(colours)


@dataclass(frozen=True)
class ComparisonMetrics:
    """Quanto duas capturas diferem, em números que dá para julgar."""

    changed_pixel_count: int
    changed_pixel_ratio: float
    maximum_channel_delta: int
    mean_channel_delta: float
    bounding_box_of_changes: tuple[int, int, int, int] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "changedPixelCount": self.changed_pixel_count,
            "changedPixelRatio": self.changed_pixel_ratio,
            "maximumChannelDelta": self.maximum_channel_delta,
            "meanChannelDelta": self.mean_channel_delta,
            "boundingBoxOfChanges": (
                list(self.bounding_box_of_changes) if self.bounding_box_of_changes else None
            ),
        }


def compare_with_golden(actual: Path, golden: Path, output: Path) -> ComparisonMetrics:
    """Compara com a baseline e publica diferença, sobreposição e métricas.

    Golden ausente é falha, não criação automática. Gerar a baseline na primeira
    execução faria o primeiro resultado — certo ou errado — virar a verdade, e
    ninguém revisaria a imagem que passou a definir o correto.
    """
    from PIL import Image, ImageChops

    if not golden.exists():
        raise CaptureError(
            DIAG_GOLDEN_MISSING,
            f"baseline ausente: {golden}. Gere com `make update-qml-goldens` e "
            "revise a imagem no commit — baseline criada sozinha nunca é revisada.",
        )

    left = _load(actual)
    right = _load(golden)
    if left.size != right.size:
        raise CaptureError(
            DIAG_CAPTURE,
            f"tamanhos diferentes: captura {left.size} vs baseline {right.size}",
        )

    difference = ImageChops.difference(left, right)
    bands = difference.split()
    total_pixels = left.width * left.height
    changed_mask = difference.convert("L").point(lambda value: 255 if value else 0)
    # Histograma em vez de percorrer pixel a pixel: a leitura é a mesma e não
    # depende do tamanho do canvas para terminar em tempo razoável.
    changed = changed_mask.histogram()[255]
    maximum = 0
    channel_sum = 0
    for band in bands:
        histogram = band.histogram()
        for value, count in enumerate(histogram):
            if count:
                maximum = max(maximum, value)
                channel_sum += value * count

    output.mkdir(parents=True, exist_ok=True)
    difference.save(output / "diff.png")
    # Sobreposição: a diferença pintada de vermelho sobre a captura. Um diff
    # cru mostra ONDE mudou; a sobreposição mostra o que mudou EM CIMA do quê,
    # que é o que permite julgar se a mudança era esperada.
    overlay = left.copy()
    overlay.paste(Image.new("RGBA", left.size, (255, 0, 0, 160)), mask=changed_mask)
    overlay.save(output / "overlay.png")
    # A baseline acompanha os artefatos para que o relatório seja auto-contido.
    # `samefile` porque nada impede o chamador de já guardar o golden aqui.
    published = output / "expected.png"
    if not (published.exists() and published.samefile(golden)):
        shutil.copyfile(golden, published)

    metrics = ComparisonMetrics(
        changed_pixel_count=changed,
        changed_pixel_ratio=round(changed / total_pixels, 6) if total_pixels else 0.0,
        maximum_channel_delta=maximum,
        mean_channel_delta=round(channel_sum / (total_pixels * len(bands)), 6)
        if total_pixels
        else 0.0,
        # Da MÁSCARA, não da diferença: o Pillow moderno usa `alpha_only=True`
        # em `getbbox()`, e o alfa da diferença é zero em toda parte quando as
        # duas imagens são opacas — devolvia None com 512 pixels alterados.
        bounding_box_of_changes=changed_mask.getbbox(),
    )
    (output / "metrics.json").write_text(
        json.dumps(metrics.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return metrics
