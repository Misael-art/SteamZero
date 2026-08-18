// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Consumidor QML de um layout já resolvido pela Theme Engine. O modelo contém
// somente nós finais: esta peça não lê read model, não calcula grid e não
// interpreta binding algum.
import QtQuick

Item {
    id: sceneRepeater

    required property var layout
    readonly property var entries: layout && layout.entries ? layout.entries : []
    readonly property int entryCount: entries.length

    readonly property url textSource: Qt.resolvedUrl("SceneText.qml")
    readonly property url imageSource: Qt.resolvedUrl("SceneImage.qml")

    function entryAt(index) {
        const loader = nodes.itemAt(index)
        return loader ? loader.item : null
    }

    Repeater {
        id: nodes
        model: sceneRepeater.entries

        delegate: Loader {
            required property var modelData

            function loadEntry() {
                if (modelData === undefined)
                    return
                const source = modelData.kind === "image"
                    ? sceneRepeater.imageSource : sceneRepeater.textSource
                // `SceneText`/`SceneImage` exigem `model` na construção. Atribuir
                // em onLoaded é tarde demais e o Qt recusa o componente.
                setSource(source, {"model": modelData})
            }

            onModelDataChanged: loadEntry()
            Component.onCompleted: loadEntry()
        }
    }
}
