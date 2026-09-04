// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Desenha uma view do IR de cena. Consome SOMENTE o grafo já materializado pela
// engine: nada aqui carrega QML, script ou shader vindo do pacote de tema, e o
// caminho de imagem chega como URI de blob já resolvido e validado no domínio.
//
// O ES-DE descreve posição e tamanho em fração da tela, e `origin` diz qual
// ponto do elemento cai sobre `pos`. Tratar `pos` como canto superior esquerdo
// desalinharia todo elemento centrado — que é a maioria dos que importam.
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts

Item {
    id: view

    // Uma view do IR: { id, elements: [...] }.
    required property var viewData
    // Elementos que a engine compilou mas este renderizador ainda não desenha.
    property alias unsupportedKinds: view.d_unsupported
    property var d_unsupported: []

    readonly property var elements: viewData && viewData.elements ? viewData.elements : []
    readonly property string viewId: viewData && viewData.id ? String(viewData.id) : ""

    // Geometria é obrigatória para desenhar. Um elemento que não declara nem
    // posição nem tamanho não é "elemento na origem em tamanho natural": é
    // elemento cuja geometria mora em algo que não chegou até aqui (variante,
    // include não resolvido). Desenhá-lo mesmo assim inventaria layout, que é
    // o que o IR se recusa a fazer — e na prática cobria a cena com uma arte
    // esticada até a tela inteira.
    function hasGeometry(element) {
        const lay = element.layout
        if (!lay) return false
        // `cropWidth`/`cropHeight` entram porque é assim que o vídeo declara
        // tamanho nos temas medidos; sem eles um vídeo em (0,0) com recorte
        // 0.28x0.33 seria lido como "sem geometria" e sumiria da cena.
        return ["x", "y", "width", "height", "maxWidth", "maxHeight",
                "cropWidth", "cropHeight", "itemWidth", "itemHeight"]
            .some(function(key) { return Number(lay[key]) > 0 })
    }

    // Tipos cuja geometria o tema declara mas cujo CONTEÚDO vem do runtime:
    // a lista de sistemas, o vídeo do jogo, os atalhos do controle. A superfície
    // desenha a estrutura e marca o conteúdo como vindo de dados, em vez de
    // inventar títulos e capas que o tema nunca prometeu.
    readonly property var dataDrivenKinds: ["carousel", "helpSystem"]

    function isDrawable(element) {
        if (!view.hasGeometry(element)) return false
        // `visible: false` é escolha do tema, não falha nossa. Contá-lo como
        // desenhado inflaria a fidelidade com um elemento que o próprio tema
        // manda esconder.
        if (element.appearance && element.appearance.visible === false) return false
        // `scope: menu` descreve o elemento COM UM MENU ABERTO. Desenhá-lo na
        // view base empilhava um segundo helpsystem sobre o do tema, com outra
        // posição e outra cor — dois conjuntos de atalhos disputando o rodapé.
        if (element.layout && element.layout.scope === "menu") return false
        if (element.kind === "image") return !!element.source
        if (element.kind === "text") return !!(element.text || element.binding)
        if (element.kind === "video") return !!element.source
        return view.dataDrivenKinds.indexOf(element.kind) !== -1
    }

    // Um elemento sem `source` resolvido e sem texto não desenha pixel. Contar
    // separado evita declarar fidelidade a partir do que foi só compilado.
    readonly property int drawnCount: {
        let n = 0
        for (let i = 0; i < elements.length; ++i) {
            if (view.isDrawable(elements[i])) n += 1
        }
        return n
    }

    // O que a engine compilou e esta superfície não desenhou, com a razão.
    readonly property var notDrawn: {
        const out = []
        for (let i = 0; i < elements.length; ++i) {
            const e = elements[i]
            if (view.isDrawable(e)) continue
            const reason = !view.hasGeometry(e)
                ? "sem geometria declarada"
                : (e.appearance && e.appearance.visible === false)
                    ? "o tema declara invisivel"
                    : (e.layout && e.layout.scope === "menu")
                        ? "escopo 'menu': so aparece com menu aberto"
                    : (["image", "text", "video"].indexOf(e.kind) === -1)
                        ? "tipo ainda nao desenhado: " + e.kind
                        : "sem asset resolvido"
            out.push({"id": e.id, "kind": e.kind, "reason": reason})
        }
        return out
    }

    // O ES-DE escreve a cor como `RRGGBBAA`; o QML lê `#AARRGGBB`. Passar a
    // string adiante sem reordenar trocaria o alfa pelo vermelho — um branco
    // opaco `ffffffff` sobreviveria por acaso, e qualquer cor com alfa não.
    function esdeColor(value, fallback) {
        if (typeof value !== "string" || value.length === 0)
            return fallback
        const hex = value.charAt(0) === "#" ? value.slice(1) : value
        if (hex.length === 8)
            return "#" + hex.slice(6, 8) + hex.slice(0, 6)
        if (hex.length === 6)
            return "#" + hex
        return fallback
    }

    function numberOr(container, key, fallback) {
        if (!container) return fallback
        const value = Number(container[key])
        return value === value ? value : fallback
    }

    Repeater {
        model: view.elements

        delegate: Loader {
            required property var modelData

            readonly property var lay: modelData.layout ? modelData.layout : ({})
            readonly property var app: modelData.appearance ? modelData.appearance : ({})

            readonly property real fx: view.numberOr(lay, "x", 0)
            readonly property real fy: view.numberOr(lay, "y", 0)
            readonly property real fw: view.numberOr(lay, "width", 0)
            readonly property real fh: view.numberOr(lay, "height", 0)
            readonly property real ox: view.numberOr(lay, "xOrigin", 0)
            readonly property real oy: view.numberOr(lay, "yOrigin", 0)

            // Largura zero em `size` significa "derive do conteúdo" no ES-DE,
            // não "invisível": cair para a tela inteira encobriria a cena, e
            // cair para zero apagaria o elemento. Deriva-se do maxSize quando há.
            readonly property real pw: fw > 0
                ? fw * view.width
                : (view.numberOr(lay, "maxWidth", 0)
                   || view.numberOr(lay, "cropWidth", 0)) * view.width
            readonly property real ph: fh > 0
                ? fh * view.height
                : (view.numberOr(lay, "maxHeight", 0)
                   || view.numberOr(lay, "cropHeight", 0)) * view.height

            x: fx * view.width - ox * width
            y: fy * view.height - oy * height
            width: pw > 0 ? pw : implicitWidth
            height: ph > 0 ? ph : implicitHeight
            z: view.numberOr(app, "layer", 0)
            opacity: view.numberOr(app, "opacity", 1)
            visible: app.visible !== false

            sourceComponent: {
                if (!view.isDrawable(modelData))
                    return null
                if (modelData.kind === "image") return imageComponent
                if (modelData.kind === "text") return textComponent
                if (modelData.kind === "video") return videoComponent
                if (modelData.kind === "carousel") return carouselComponent
                return helpComponent
            }

            Component {
                id: imageComponent
                Image {
                    source: modelData.source
                    // `tile` e o resto do IR pedem preenchimento distinto; sem
                    // isto um fundo 1x1 esticaria em vez de repetir.
                    fillMode: lay.tile === true ? Image.Tile : Image.PreserveAspectFit
                    asynchronous: true
                    cache: true
                    smooth: true
                }
            }


            // O carrossel é dirigido por dados: os itens são os sistemas ou os
            // jogos, que esta superfície não tem. Desenhar a ESTRUTURA — moldura
            // e os `maxItemCount` compartimentos no tamanho declarado — mostra o
            // layout que o tema pediu sem inventar capas que ele nunca prometeu.
            Component {
                id: carouselComponent
                Item {
                    readonly property int slots: Math.max(
                        1, Math.min(12, Math.round(view.numberOr(lay, "maxItemCount", 3))))
                    readonly property real slotW: view.numberOr(lay, "itemWidth", 0.12) * view.width
                    readonly property real slotH: view.numberOr(lay, "itemHeight", 0.18)
                        * view.height
                    readonly property real gap: Math.max(
                        4, view.numberOr(lay, "itemMarginX", 0.01) * view.width)

                    Rectangle {
                        anchors.fill: parent
                        color: view.esdeColor(app.color, "#00000000")
                    }
                    Row {
                        anchors.centerIn: parent
                        spacing: parent.gap
                        Repeater {
                            model: parent.parent.slots
                            delegate: Rectangle {
                                width: slotW
                                height: slotH
                                radius: view.numberOr(lay, "imageCornerRadius", 0) * view.width
                                color: "#14212e"
                                border.color: view.esdeColor(app.textColor, "#3a4c5e")
                                border.width: 1
                                Text {
                                    anchors.centerIn: parent
                                    text: "{item}"
                                    color: view.esdeColor(app.textColor, "#9eabba")
                                    font.pixelSize: Math.max(
                                        10, view.numberOr(lay, "fontSize", 0.02) * view.height)
                                }
                            }
                        }
                    }
                }
            }

            // O vídeo entra por Loader dinâmico, e não por `import QtMultimedia`
            // no topo: um host sem o módulo faria a CENA INTEIRA falhar ao
            // carregar, e a regra é que falha degrada e nunca trava. Sem o
            // módulo, o quadro fica com a cor declarada e o motivo aparece.
            Component {
                id: videoComponent
                Item {
                    id: videoHost
                    property var player: null
                    readonly property bool multimediaReady: player !== null && player.ready

                    Rectangle {
                        anchors.fill: parent
                        color: view.esdeColor(app.color, "#0b1118")
                        visible: !videoHost.multimediaReady
                        Text {
                            anchors.centerIn: parent
                            text: videoHost.player === null
                                ? qsTr("vídeo indisponível")
                                : qsTr("vídeo não reproduziu")
                            color: "#9eabba"
                            font.pixelSize: 12
                        }
                    }

                    Component.onCompleted: {
                        // `ready` observa a REPRODUCAO, nao a criacao do objeto:
                        // marcar pronto so porque o componente instanciou fazia o
                        // quadro degradado nunca aparecer, e uma falha silenciosa
                        // virava retangulo em branco sem explicacao nenhuma.
                        // A fonte vem do id da raiz. MediaPlayer nao e item visual,
                        // entao o encadeamento por hierarquia nao resolve para o Item
                        // que o contem: a fonte ficava vazia e o video nunca
                        // carregava, com o quadro degradado dizendo a verdade sobre um
                        // defeito que era nosso, nao do host.
                        const source = 'import QtQuick; import QtMultimedia; Item {'
                            + ' id: root; property url clip;'
                            + ' readonly property bool ready: mp.error === MediaPlayer.NoError'
                            + ' && mp.mediaStatus >= MediaPlayer.LoadedMedia;'
                            + ' anchors.fill: parent;'
                            + ' MediaPlayer { id: mp; source: root.clip; loops: MediaPlayer.Infinite;'
                            + ' videoOutput: out; Component.onCompleted: play() }'
                            + ' VideoOutput { id: out; anchors.fill: parent;'
                            + ' fillMode: VideoOutput.PreserveAspectCrop } }'
                        try {
                            const item = Qt.createQmlObject(source, videoHost, "esdeVideo")
                            item.clip = modelData.source
                            videoHost.player = item
                        } catch (error) {
                            // Sem QtMultimedia: o quadro degradado acima fica.
                            videoHost.player = null
                        }
                    }
                }
            }

            // Os atalhos vêm do runtime (quais botões valem naquela tela), então
            // a superfície desenha as ENTRADAS com o espaçamento e a cor do tema
            // e marca o conteúdo como dado. Escrever "A: Selecionar" aqui seria
            // afirmar um mapeamento que o tema não declara.
            Component {
                id: helpComponent
                Row {
                    spacing: Math.max(6, view.numberOr(lay, "entrySpacing", 0.01) * view.width)
                    Repeater {
                        model: 3
                        delegate: Row {
                            spacing: Math.max(
                                3, view.numberOr(lay, "iconTextSpacing", 0.004) * view.width)
                            Rectangle {
                                width: helpText.font.pixelSize
                                height: width
                                radius: width / 2
                                color: view.esdeColor(app.iconColor, "#cccccc")
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                id: helpText
                                text: "{ação}"
                                color: view.esdeColor(app.textColor, "#cccccc")
                                font.pixelSize: Math.max(
                                    10, view.numberOr(lay, "fontSize", 0.03) * view.height
                                        * view.numberOr(lay, "entryRelativeScale", 1))
                            }
                        }
                    }
                }
            }

            Component {
                id: textComponent
                Text {
                    // `binding` é dado de jogo, que esta superfície não tem: o
                    // rótulo do vínculo é honesto sobre isso, e inventar um
                    // título faria a prévia mentir sobre o que o tema mostra.
                    text: modelData.text
                        ? modelData.text
                        : "{" + String(modelData.binding.field ? modelData.binding.field
                                                              : modelData.binding) + "}"
                    color: view.esdeColor(app.color, "#e8eef6")
                    font.pixelSize: Math.max(10, view.numberOr(lay, "fontSize", 0.035)
                                                 * view.height)
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }
}
