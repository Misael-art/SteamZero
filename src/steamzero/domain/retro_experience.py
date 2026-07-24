# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Catálogo declarativo de presets da experiência retro."""

from __future__ import annotations

from typing import Any

from steamzero.api import contracts
from steamzero.domain.integer_scaling import normative_table

_FIELDS = (
    ("scalingMode", "Escala", "ready"),
    ("fallbackFilter", "Fallback", "ready"),
    ("crop", "Corte", "ready"),
    ("stretch", "Esticar imagem", "ready"),
    ("pixelAspect", "Proporção de pixel", "planned"),
    ("colorProfile", "Perfil de cores", "planned"),
    ("displayShader", "Shader de tela", "planned"),
    ("signalPath", "Caminho de sinal", "planned"),
    ("timingPolicy", "Timing", "planned"),
    ("slowdownPolicy", "Slowdown original", "planned"),
    ("overclockPolicy", "Overclock", "planned"),
)
_DETAILS = {
    "scalingMode": "Política primária de redimensionamento.",
    "fallbackFilter": "Filtro usado quando integer-fit não atende ao viewport.",
    "crop": "Permite ou recusa remover bordas da imagem.",
    "stretch": "Permite ou recusa distorcer a razão geométrica.",
    "pixelAspect": "Tratamento de PAR será efetivado no R2.",
    "colorProfile": "Cores por hardware/tela serão efetivadas no R2.",
    "displayShader": "CRT/LCD e disponibilidade serão efetivados no R2.",
    "signalPath": "RF, composto e RGB serão efetivados no R2.",
    "timingPolicy": "Fonte de timing e DRC serão efetivados no R3.",
    "slowdownPolicy": "Slowdown histórico será efetivado no R3.",
    "overclockPolicy": "Overclock permanece desligado ou opt-in no R3.",
}
_DISPLAY = {
    "integer": "Integer scale",
    "sharp-bilinear": "Sharp-bilinear",
    "hardware-native": "PAR do hardware",
    "corrected": "PAR corrigido",
    "hardware-original": "Cores do hardware",
    "neutral": "Cores neutras",
    "enhanced": "Cores realçadas",
    "authentic": "Shader histórico",
    "subtle": "Shader sutil",
    "off": "Desligado",
    "historical": "Sinal histórico",
    "clean-rgb": "RGB limpo",
    "registry-native": "Timing nativo do registry",
    "preserve": "Preservar",
    "opt-in": "Somente opt-in",
}
_PRESETS = (
    (
        "como-era",
        "Como era",
        "Apresentação histórica, sem melhorias ocultas.",
        "original",
        {
            "scalingMode": "integer",
            "fallbackFilter": "sharp-bilinear",
            "crop": False,
            "stretch": False,
            "pixelAspect": "hardware-native",
            "colorProfile": "hardware-original",
            "displayShader": "authentic",
            "signalPath": "historical",
            "timingPolicy": "registry-native",
            "slowdownPolicy": "preserve",
            "overclockPolicy": "off",
        },
    ),
    (
        "equilibrado",
        "Equilibrado",
        "Legibilidade moderna conservando geometria e timing.",
        "balanced",
        {
            "scalingMode": "integer",
            "fallbackFilter": "sharp-bilinear",
            "crop": False,
            "stretch": False,
            "pixelAspect": "corrected",
            "colorProfile": "neutral",
            "displayShader": "subtle",
            "signalPath": "clean-rgb",
            "timingPolicy": "registry-native",
            "slowdownPolicy": "preserve",
            "overclockPolicy": "off",
        },
    ),
    (
        "melhorado",
        "Melhorado",
        "Imagem ampliada e melhorias identificadas como não originais.",
        "enhanced",
        {
            "scalingMode": "sharp-bilinear",
            "fallbackFilter": "sharp-bilinear",
            "crop": False,
            "stretch": False,
            "pixelAspect": "corrected",
            "colorProfile": "enhanced",
            "displayShader": "off",
            "signalPath": "clean-rgb",
            "timingPolicy": "registry-native",
            "slowdownPolicy": "preserve",
            "overclockPolicy": "opt-in",
        },
    ),
)


def preset_catalog(
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> dict[str, Any]:
    presets = []
    for preset_id, label, summary, originality, settings in _PRESETS:
        differences = [
            {
                "key": key,
                "label": field_label,
                "value": _display_value(settings[key]),
                "detail": _DETAILS[key],
                "readiness": readiness,
                "originality": originality,
            }
            for key, field_label, readiness in _FIELDS
        ]
        presets.append(
            {
                "id": preset_id,
                "label": label,
                "summary": summary,
                "recommended": preset_id == "equilibrado",
                "originality": originality,
                "settings": dict(settings),
                "differences": differences,
            }
        )
    payload = {
        "schemaVersion": 1,
        "contractId": "retro-experience-v1",
        "truthState": "declarative",
        "scalingTable": normative_table(viewport_width, viewport_height),
        "presets": presets,
    }
    contracts.validate(payload, "retro-experience-v1.schema.json")
    return payload


def _display_value(value: object) -> str:
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    return _DISPLAY[str(value)]
