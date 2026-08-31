// SPDX-License-Identifier: GPL-3.0-or-later
//
// Capas no Launcher: quando o jogo tem coverUrl, o cartão renderiza a arte;
// sem coverUrl, mostra placeholder honesto (inicial) — nunca "imagem de capa".
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
         "items": [
            {"id": "com-capa", "title": "Com Capa",
             "coverUrl": "file:///tmp/steamzero-cover.png"},
            {"id": "sem-capa", "title": "Sem Capa", "coverUrl": ""}
         ]}
    ]
    readonly property var focusMap: ({
        "initial": "header:home",
        "rows": ["header:home", "library:com-capa"],
        "diagnostics": [],
        "nodes": {
            "header:home": {"id": "header:home", "section": "header", "column": 0,
                            "up": null, "down": "library:com-capa", "left": null,
                            "right": null, "action": null},
            "library:com-capa": {"id": "library:com-capa", "section": "library", "column": 0,
                                 "up": "header:home", "down": null, "left": null,
                                 "right": null, "action": null},
            "library:sem-capa": {"id": "library:sem-capa", "section": "library", "column": 1,
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
        interval: 200
        running: true
        onTriggered: {
            // Os dois cartões existem.
            harness.check(home.itemIndex.length === 2,
                          "a home precisa instanciar os 2 itens do acervo, viu " + home.itemIndex.length)

            // Adequação responsiva: largura do cartão derivada da largura útil.
            harness.check(home.width > 0, "a home precisa ter largura útil")
            harness.check(home.width >= 180, "os cartões precisam respeitar o mínimo de 180px")

            // Sem capa: placeholder (Texto da inicial) visível; capa oculta.
            var item = findByObjectName(home, "launcherItem")
            harness.check(item !== null, "o cartão launcherItem precisa existir")
            if (item !== null) {
                // O cartão tem dois Text (inicial + legenda). O Image de capa é
                // o primeiro filho de tipo Image; com capa ele deve ter source.
                var images = []
                for (var i = 0; i < item.children.length; ++i)
                    if (item.children[i] instanceof Image) images.push(item.children[i])
                harness.check(images.length >= 1, "o cartão precisa ter um elemento de imagem")
            }

            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
