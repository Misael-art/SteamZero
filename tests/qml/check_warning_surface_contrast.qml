// SPDX-License-Identifier: GPL-3.0-or-later
// UX-01: o texto dos avisos precisa continuar legível no tema ativo.
//
// A Central pinta vários avisos sobre superfícies fixas (o banner de perfil, o
// rodapé de navegação, o cartão de conflito, o aviso de leitura parcial). A
// tinta é escolhida por `_contrastTextColor(surface)`, que deveria devolver a
// das duas cores do tema que contrasta mais com aquela superfície. Quando o
// argumento chega como texto em vez de cor, a razão vira NaN, toda comparação
// falha e a função degenera para "sempre backgroundColor" — que em tema escuro
// é escuro, e o aviso desaparece. É exatamente o que a auditoria de 2026-09-26
// registrou como "banner/footer de baixo contraste" com o tema ativo escuro.
//
// Este harness prova a regra nos três modos que a Central pode estar: tema
// escuro, tema claro e alto contraste.
import QtQuick
import "../../src/steamzero/ui/qml"

Main {
    id: window
    visible: true
    width: 1280
    height: 800

    property int failures: 0
    property int checks: 0
    property int firstFailure: 0
    property int phase: 0

    /// Superfícies fixas usadas pelos avisos do shell.
    readonly property var warningSurfaces: [
        "#24180b",  // banner de perfil / cartão de conflito / leitura parcial
        "#211a10",  // botão de atenção da navegação
        "#080d13",  // rodapé de navegação
        "#352020",  // aviso de erro da central
        "#35171b",  // retorno de ação com erro
        "#102b20"   // retorno de ação concluída
    ]

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        if (firstFailure === 0)
            firstFailure = checks
        failures += 1
        console.error("FAIL: " + message)
    }

    function themeFixture(colors, highContrast) {
        return {
            "truthState": "stale",
            "desiredProfile": "handheld-desktop",
            "appliedProfile": "handheld-desktop",
            "observedProfile": "handheld-desktop",
            "recommendedProfile": "handheld-desktop",
            "statusReasons": ["Motivo sintético de teste."],
            "recoveryRequired": false,
            "independentRuntime": true,
            "context": {"deviceKind": "deck-lcd", "displays": [], "capabilities": [], "conflicts": []},
            "dashboard": {
                "accessibility": {"reducedMotion": true, "highContrast": highContrast},
                "theme": {
                    "resolved": {
                        "themeId": "org.steamzero.fixture",
                        "themeVersion": "1.0.0",
                        "highContrast": highContrast,
                        "reducedMotion": true,
                        "resolved": {"color": colors}
                    }
                },
                "components": [],
                "steam": [],
                "sync": {"pending": 0, "conflicted": 0, "done": 0, "items": []},
                "doctor": {"state": "ready", "checks": []},
                "playtime": [],
                "collections": {"state": "empty", "collections": []},
                "libraryHealth": {
                    "state": "empty",
                    "counts": {"verified": 0, "unchecked": 0, "suspect": 0, "missing": 0, "error": 0},
                    "items": []
                },
                "emulation": {"state": "empty", "systems": []},
                "steamGameplay": {"state": "empty"},
                "uiContracts": {"byId": {}}
            }
        }
    }

    /// Mesma fórmula do produto, reimplementada em Python em
    /// tests/unit/test_ui_attention_surface_contrast.py: se uma das duas
    /// derivar, as duas precisam derivar juntas.
    function ratioOf(first, second) {
        return window._contrastRatio(first, second)
    }

    function assertSurfacesLegible(label, minimum) {
        for (let i = 0; i < warningSurfaces.length; i++) {
            const surface = warningSurfaces[i]
            const ratio = ratioOf(window._contrastTextColor(surface), surface)
            check(ratio === ratio, `${label}: razão NaN em ${surface} — a superfície chegou como texto`)
            check(ratio >= minimum,
                  `${label}: tinta sobre ${surface} fica em ${ratio.toFixed(2)}:1, mínimo ${minimum}:1`)
        }
    }

    function runPhase() {
        if (phase >= 4)
            return
        if (phase === 0) {
            window.desktopStatus = themeFixture({
                "background": "#0b1020", "sidebar": "#0d1326", "surface": "#141a2e",
                "surfaceRaised": "#1c2440", "surfaceSelected": "#1a2542", "border": "#262f4d",
                "text": "#e8ecf7", "textMuted": "#8b93a8", "textDisabled": "#5d6579",
                "accent": "#22d3ee", "accentStrong": "#0e7490", "success": "#59d35d",
                "successSurface": "#16301c", "warning": "#ff9f1a", "warningSurface": "#3b2a0e",
                "danger": "#ff6b73", "dangerSurface": "#3b1619", "focus": "#22d3ee"
            }, false)
            check(String(window.backgroundColor).toLowerCase() === "#0b1020",
                  "o tema escuro sintético precisa estar aplicado, senão a medição é falsa")
            check(String(window.textColor).toLowerCase() === "#e8ecf7",
                  "texto do tema escuro não chegou ao shell")
            // No tema escuro a resposta correta é o texto claro, nunca o fundo.
            check(String(window._contrastTextColor("#24180b")).toLowerCase() === "#e8ecf7",
                  "em tema escuro o aviso tem de usar a tinta clara do tema")
            assertSurfacesLegible("tema escuro", 4.5)
            phase = 1
            return
        }
        if (phase === 1) {
            window.desktopStatus = themeFixture({
                "background": "#e7eceb", "sidebar": "#d8dfdf", "surface": "#f4f7f5",
                "surfaceRaised": "#ffffff", "surfaceSelected": "#dce8e8", "border": "#aebdbe",
                "text": "#16212a", "textMuted": "#53616b", "textDisabled": "#7a878b",
                "accent": "#006f99", "accentStrong": "#005471", "success": "#167a45",
                "successSurface": "#dff3e7", "warning": "#9a5a00", "warningSurface": "#fff0d5",
                "danger": "#ae2634", "dangerSurface": "#fbe2e5", "focus": "#006f99"
            }, false)
            check(String(window.backgroundColor).toLowerCase() === "#e7eceb",
                  "o tema claro sintético precisa estar aplicado")
            // Aqui a resposta correta é o fundo claro: o texto escuro do tema
            // desapareceria sobre a superfície do aviso.
            check(String(window._contrastTextColor("#24180b")).toLowerCase() === "#e7eceb",
                  "em tema claro o aviso tem de usar o fundo claro como tinta")
            assertSurfacesLegible("tema claro", 4.5)
            phase = 2
            return
        }
        if (phase === 2) {
            window.desktopStatus = themeFixture({
                "background": "#0b1020", "text": "#e8ecf7", "surface": "#141a2e"
            }, true)
            check(window.highContrast === true, "alto contraste do tema deve ativar a preferência")
            check(String(window.textColor).toLowerCase() === "#ffffff"
                  && String(window.backgroundColor).toLowerCase() === "#000000",
                  "alto contraste deve reescrever texto e fundo para preto/branco puros")
            assertSurfacesLegible("alto contraste", 7.0)
            phase = 3
            return
        }
        check(checks > 0, "o harness precisa executar ao menos uma verificação")
        // Registrar o denominador: um log vazio não distingue "passou" de
        // "não rodou".
        console.log(`OK: ${checks} verificações de contraste, ${failures} falhas`)
        phase = 4
        Qt.exit(failures === 0 ? 0 : firstFailure)
    }

    Timer {
        interval: 20
        repeat: true
        running: true
        onTriggered: window.runPhase()
    }
}
