// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Home fullscreen do AURA Launcher.
//
// O foco anda pelo mapa já resolvido no domínio: este componente lê
// `focusMap.nodes[atual][direção]` e aplica. Ele não escolhe vizinho, não
// deduz coluna e não inventa destino — se o QML decidisse vizinhança, a
// garantia de "sem becos" provada no domínio não valeria para o que o usuário
// realmente navega.
//
// Direção sem destino mantém o foco onde está. Não é omissão: mover para um
// destino nulo apagaria o foco e, num aparelho sem mouse, isso é a própria
// definição de beco.

import QtQuick

Item {
    id: home

    // Mapa vindo de `FocusMap.to_qml_object()`.
    required property var focusMap
    // Seções já ordenadas: [{id, title, items: [{id, title}]}].
    required property var sections

    property string currentFocus: focusMap && focusMap.initial ? focusMap.initial : ""
    // Preferências de acessibilidade herdadas do host (highContrast etc.).
    property var accessibility: ({"highContrast": false, "visualScale": 1.0, "reducedMotion": false})

    // Em alto contraste o Launcher usa os mesmos valores da central (UiTokens
    // highContrast): texto branco, acento claro, borda forte e fundo quase
    // preto. Fora disso mantém o tema atual — sem refatorar para tokens, para
    // não arriscar o layout da release.
    function _hc(lightValue, highContrastValue) {
        return home.accessibility && home.accessibility.highContrast
            ? highContrastValue : lightValue
    }

    readonly property var currentNode: focusMap && focusMap.nodes
        ? focusMap.nodes[currentFocus] : undefined
    readonly property int focusedItemCount: itemIndex.length
    readonly property bool empty: currentNode !== undefined
        && currentNode.action !== null && currentNode.action !== undefined

    // Índice plano das chaves de item, derivado das seções.
    //
    // A primeira versão disto era um array preenchido por `push` no
    // `Component.onCompleted` de cada delegate. Parecia funcionar e não
    // funcionava: bastou outro binding passar a ler a propriedade para o
    // binding original reavaliar, zerando o array. Derivar dos dados é
    // determinístico e não depende da ordem de instanciação.
    readonly property var itemIndex: {
        const keys = []
        if (!sections)
            return keys
        for (let s = 0; s < sections.length; ++s) {
            const section = sections[s]
            if (!section || !section.items)
                continue
            for (let i = 0; i < section.items.length; ++i)
                keys.push(home._nodeId(section.id, section.items[i].id))
        }
        return keys
    }
    // Quantos itens estão destacados e qual: mais de um significa que a chave
    // do item divergiu da chave do mapa, e o usuário veria dois focos.
    readonly property int highlightedCount: {
        let total = 0
        for (let i = 0; i < itemIndex.length; ++i)
            if (itemIndex[i] === currentFocus)
                total += 1
        return total
    }
    readonly property string highlightedNode:
        itemIndex.indexOf(currentFocus) >= 0 ? currentFocus : ""

    function move(direction) {
        const node = focusMap && focusMap.nodes ? focusMap.nodes[currentFocus] : undefined
        if (node === undefined)
            return false
        const target = node[direction]
        if (target === null || target === undefined)
            return false
        if (focusMap.nodes[target] === undefined)
            return false
        currentFocus = target
        return true
    }

    Keys.onUpPressed: move("up")
    Keys.onDownPressed: move("down")
    Keys.onLeftPressed: move("left")
    Keys.onRightPressed: move("right")
    focus: true

    Column {
        id: rows
        anchors.fill: parent
        anchors.margins: 24
        spacing: 18

        Text {
            objectName: "launcherHeader"
            text: qsTr("Início")
            color: home.currentFocus === "header:home"
                ? home._hc("#22d3ee", "#55d8ff") : home._hc("#8b93a8", "#c6d0db")
            font.pixelSize: 20
        }

        Repeater {
            model: home.sections
            delegate: Column {
                id: sectionColumn
                required property var modelData
                // Guardar o id aqui evita subir a cadeia de `parent` a partir
                // do delegate interno, que quebra em silêncio se a árvore
                // visual mudar de forma.
                readonly property string sectionId: modelData.id
                spacing: 6
                Text {
                    text: sectionColumn.modelData.title
                    color: home._hc("#8b93a8", "#c6d0db")
                    font.pixelSize: 13
                }
                Flow {
                    spacing: 12
                    Repeater {
                        model: sectionColumn.modelData.items
                        delegate: Rectangle {
                            required property var modelData
                            readonly property string nodeId:
                                home._nodeId(sectionColumn.sectionId, modelData.id)
                            objectName: "launcherItem"
                            // Cartão responsivo: largura derivada da largura
                            // útil da área, mínimo 180px, máximo 280px. Em 1080p
                            // a grade redistribui colunas em vez de fixar 180px.
                            width: Math.min(Math.max(home.width / (Math.max(3, Math.floor(home.width / 240))) - 14, 180), 280)
                            height: 132
                            radius: 10
                            color: home._hc("#0b1622", "#03080c")
                            border.width: home.currentFocus === nodeId ? 3 : 1
                            border.color: home.currentFocus === nodeId
                                ? home._hc("#22d3ee", "#55d8ff") : home._hc("#243044", "#68839b")
                            clip: true
                            // Capa do jogo, quando o scraping/mídia a produziu.
                            Image {
                                anchors.fill: parent
                                visible: !!modelData.coverUrl
                                source: modelData.coverUrl || ""
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                // Limita a decodificação à resolução útil: evita
                                // o pico de memória de decodificar a arte nativa.
                                sourceSize.width: width * 2
                                sourceSize.height: height * 2
                            }
                            // Placeholder honesto quando não há arte: um retângulo
                            // com a inicial do sistema, nunca imagem "de capa".
                            Text {
                                anchors.fill: parent
                                visible: !modelData.coverUrl
                                text: String(modelData.title || "?").charAt(0)
                                color: home._hc("#8b93a8", "#c6d0db")
                                font.pixelSize: 48
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                            Text {
                                // Legenda sobre a capa (ou sobre o placeholder).
                                anchors.fill: parent
                                anchors.bottomMargin: 6
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                verticalAlignment: Text.AlignBottom
                                text: modelData.title
                                color: home._hc("#f2f6fb", "#ffffff")
                                font.pixelSize: 13
                                wrapMode: Text.Wrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                style: Text.Outline
                                styleColor: home._hc("#000000", "#000000")
                            }
                        }
                    }
                }
            }
        }
    }

    // A chave do nó é montada do mesmo jeito no domínio e aqui. Um dia isso
    // deve vir declarado no próprio item, como o `previewKey` do Studio.
    function _nodeId(sectionId, itemId) {
        return sectionId + ":" + itemId
    }
}
