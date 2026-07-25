// SPDX-License-Identifier: GPL-3.0-or-later
// Alto contraste vem do host (dashboard.accessibility.highContrast) e reescreve
// as mesmas propriedades de cor que todo o QML já consome — nenhum consumidor
// precisa saber da preferência.
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
    property var normalColors: null

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        if (firstFailure === 0)
            firstFailure = checks
        failures += 1
        console.error("FAIL: " + message)
    }

    function snapshotColors() {
        return {
            "background": String(window.backgroundColor),
            "surface": String(window.surfaceColor),
            "border": String(window.borderColor),
            "text": String(window.textColor),
            "muted": String(window.mutedColor)
        }
    }

    function statusWith(accessibility) {
        return {
            "dashboard": {
                "accessibility": accessibility,
                "uiContracts": {"byId": {}},
                "components": [],
                "steam": [],
                "collections": {"state": "degraded", "collections": []}
            }
        }
    }

    function runPhase() {
        if (phase === 0) {
            // Sem payload de acessibilidade: o padrão não pode ser alto contraste.
            window.desktopStatus = statusWith({})
            check(window.highContrast === false,
                  "accessibility vazio deve degradar para alto contraste desligado")
            check(window.reducedMotion === false,
                  "accessibility vazio deve degradar para reducedMotion desligado")
            normalColors = snapshotColors()
            phase = 1
            return
        }
        if (phase === 1) {
            window.desktopStatus = statusWith({"reducedMotion": false, "highContrast": true})
            check(window.highContrast === true,
                  "highContrast=true do host deve ativar a preferência")
            const strong = snapshotColors()
            check(strong.background !== normalColors.background,
                  "fundo deve mudar em alto contraste")
            check(strong.border !== normalColors.border,
                  "borda deve mudar em alto contraste")
            check(strong.text !== normalColors.text,
                  "texto deve mudar em alto contraste")
            check(String(window.textColor) === "#ffffff",
                  "texto em alto contraste deve ser branco puro")
            check(String(window.backgroundColor) === "#000000",
                  "fundo em alto contraste deve ser preto puro")
            check(String(window.borderColor) === "#ffffff",
                  "borda em alto contraste deve ser branca")
            phase = 2
            return
        }
        if (phase === 2) {
            // A preferência é do host: desligar no host desliga na UI.
            window.desktopStatus = statusWith({"reducedMotion": false, "highContrast": false})
            check(window.highContrast === false,
                  "highContrast=false do host deve desativar a preferência")
            const back = snapshotColors()
            check(back.background === normalColors.background,
                  "fundo deve voltar ao tema padrão")
            check(back.text === normalColors.text,
                  "texto deve voltar ao tema padrão")
            phase = 3
            return
        }
        check(checks > 0, "o harness precisa executar ao menos uma verificação")
        Qt.exit(failures === 0 ? 0 : firstFailure)
    }

    Timer {
        interval: 20
        repeat: true
        running: true
        onTriggered: window.runPhase()
    }
}
