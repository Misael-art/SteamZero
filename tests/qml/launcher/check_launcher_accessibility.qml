// SPDX-License-Identifier: GPL-3.0-or-later
//
// Acessibilidade herdada no Launcher: quando o host reporta alto contraste, a
// home e a página de jogo trocam as cores fixas pelos valores high-contrast da
// central (UiTokens) — sem refatorar para tokens, para não arriscar o layout.
// Se o QML ignorar `accessibility.highContrast`, o usuário que configurou alto
// contraste no Plasma continuaria vendo o tema escuro padrão.
import QtQuick
import "../../../src/steamzero/ui/qml/launcher"

Item {
    id: harness
    width: 1280
    height: 800

    property int failures: 0
    property int checkIndex: 0
    function check(condition, message) {
        checkIndex += 1
        if (!condition) {
            failures += 1
            console.error("FAIL #" + checkIndex + ": " + message)
        }
    }

    readonly property var sections: [
        {"id": "library", "title": "Biblioteca",
         "items": [{"id": "celeste", "title": "Celeste"}]}
    ]
    readonly property var focusMap: ({
        "initial": "header:home",
        "rows": ["header:home", "library:celeste"],
        "diagnostics": [],
        "nodes": {
            "header:home": {"id": "header:home", "section": "header", "column": 0,
                            "up": null, "down": "library:celeste", "left": null,
                            "right": null, "action": null},
            "library:celeste": {"id": "library:celeste", "section": "library", "column": 0,
                                "up": "header:home", "down": null, "left": null,
                                "right": null, "action": null}
        }
    })

    LauncherHome {
        id: home
        anchors.fill: parent
        focusMap: harness.focusMap
        sections: harness.sections
    }

    function highContrastPayload() {
        return ({"highContrast": true, "visualScale": 1.0, "reducedMotion": false})
    }

    function findByObjectName(node, name) {
        if (node === null || node === undefined)
            return null
        if (node.objectName === name)
            return node
        for (var i = 0; i < node.children.length; ++i) {
            var found = findByObjectName(node.children[i], name)
            if (found !== null)
                return found
        }
        return null
    }

    Timer {
        interval: 80
        running: true
        onTriggered: {
            // Sem alto contraste: `_hc` devolve o valor original (tema atual).
            harness.check(home._hc("#f2f6fb", "#ffffff") === "#f2f6fb",
                          "sem highContrast texto claro permanece o original")
            harness.check(home._hc("#22d3ee", "#55d8ff") === "#22d3ee",
                          "sem highContrast o acento é o original")

            // Aplicar highContrast e reler: agora devolve a variante acessível.
            home.accessibility = harness.highContrastPayload()
            harness.check(home._hc("#f2f6fb", "#ffffff") === "#ffffff",
                          "home._hc deve trocar texto claro por branco em highContrast")
            harness.check(home._hc("#8b93a8", "#c6d0db") === "#c6d0db",
                          "home._hc deve trocar muted por muted-highContrast")
            harness.check(home._hc("#0b1622", "#03080c") === "#03080c",
                          "home._hc deve trocar fundo escuro por quase-preto")
            harness.check(home._hc("#22d3ee", "#55d8ff") === "#55d8ff",
                          "com highContrast o acento vira a variante clara")

            // Ler a cor real do cabeçalho (deve refletir o alto contraste).
            var header = findByObjectName(home, "launcherHeader")
            harness.check(header !== null, "o cabeçalho da home precisa existir para a leitura")
            if (header !== null) {
                harness.check(header.color.toString() === "#55d8ff",
                              "cabeçalho focado em highContrast deve ser #55d8ff, é " + header.color)
            }

            // Desligar de volta: a home volta ao tema original.
            home.accessibility = ({"highContrast": false, "visualScale": 1.0, "reducedMotion": false})
            harness.check(home._hc("#8b93a8", "#c6d0db") === "#8b93a8",
                          "desligar highContrast restaura a cor muted original")

            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
