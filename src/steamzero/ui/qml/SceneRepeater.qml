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

    function outlineAt(index) {
        return outlines.itemAt(index)
    }

    // Moldura de destaque do item central (e dos vizinhos, quando o tema declara
    // tratamento). Largura, cor e visibilidade chegam resolvidas; o QML não
    // decide quem é o centro nem quanto contorno aplicar.
    Repeater {
        id: outlines
        model: sceneRepeater.entries

        delegate: Rectangle {
            required property var modelData
            readonly property real outlineWidth: modelData && modelData.outlineWidth !== undefined
                ? Number(modelData.outlineWidth) : 0

            x: modelData.x
            y: modelData.y
            width: modelData.width !== undefined ? modelData.width : 0
            height: modelData.height !== undefined ? modelData.height : 0
            z: (modelData.z !== undefined ? modelData.z : 0) - 1
            scale: modelData.scale !== undefined ? modelData.scale : 1
            visible: outlineWidth > 0 && modelData.visible !== false
            color: "transparent"
            border.width: outlineWidth
            border.color: modelData.outlineColor !== undefined ? modelData.outlineColor : "#ffffff"
            radius: 4
        }
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
