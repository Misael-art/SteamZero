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

    // Conteúdo publicado pelo dashboard. A cena continua sendo declarativa:
    // este modelo só contém valores já projetados (jogos, mídia e ações), e
    // nunca caminhos arbitrários para QML, scripts ou executáveis.
    property var runtimeModel: ({})
    property bool reducedMotion: false
    property bool highContrast: false

    // A cena pode ser usada como uma superfície interativa sem ganhar regras
    // próprias de catálogo. O IR continua sendo a fonte da geometria; esta
    // camada só percorre os elementos que o IR marcou como dados de interação.
    property bool interactive: false
    property color focusColor: "#13bdf2"
    property int currentFocusIndex: -1
    signal elementFocused(string elementId)
    signal elementActivated(string elementId)
    // Eventos semânticos da biblioteca. A cena não decide o que "Jogar" faz;
    // apenas informa ao shell qual registro sanitizado recebeu foco/ativação.
    signal itemFocused(string itemId)
    signal itemActivated(string itemId)

    property int activeItemIndex: 0

    readonly property var focusableElements: {
        const out = []
        for (let i = 0; i < view.elements.length; ++i) {
            const element = view.elements[i]
            if (view.isFocusable(element)) out.push(element)
        }
        return out
    }

    readonly property string currentFocusId: {
        const element = view.focusableElements[view.currentFocusIndex]
        return element && element.id ? String(element.id) : ""
    }

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
    readonly property var dataDrivenKinds: ["carousel", "helpSystem", "rating", "badges",
        "systemStatus", "textList", "grid", "gameListInfo", "gameSelector"]

    readonly property var runtimeItems: runtimeModel && Array.isArray(runtimeModel.items)
        ? runtimeModel.items : []
    readonly property var selectedItem: view.runtimeItems.length > 0
        && view.activeItemIndex >= 0
        && view.activeItemIndex < view.runtimeItems.length
        ? view.runtimeItems[view.activeItemIndex]
        : (runtimeModel && runtimeModel.selected ? runtimeModel.selected : ({}))

    function syncRuntimeSelection() {
        const raw = runtimeModel && runtimeModel.selectedIndex !== undefined
            ? Number(runtimeModel.selectedIndex) : 0
        const requested = raw === raw ? Math.floor(raw) : 0
        if (view.runtimeItems.length === 0) {
            view.activeItemIndex = 0
            return
        }
        view.activeItemIndex = Math.max(0, Math.min(requested, view.runtimeItems.length - 1))
    }

    function focusedRuntimeKind() {
        if (view.currentFocusIndex < 0 || view.currentFocusIndex >= view.focusableElements.length)
            return ""
        const element = view.focusableElements[view.currentFocusIndex]
        return element && element.kind ? String(element.kind) : ""
    }

    function moveRuntimeItem(direction) {
        if (view.runtimeItems.length < 2)
            return false
        if (direction !== "left" && direction !== "right")
            return false
        const delta = direction === "left" ? -1 : 1
        let next = view.activeItemIndex + delta
        if (next < 0)
            next = view.runtimeItems.length - 1
        if (next >= view.runtimeItems.length)
            next = 0
        view.activeItemIndex = next
        const item = view.runtimeItems[next]
        if (item && item.id !== undefined)
            view.itemFocused(String(item.id))
        return true
    }

    function bindingValue(binding, item) {
        if (!binding) return ""
        const source = typeof binding === "string" ? "item" : String(binding.source || "item")
        const field = typeof binding === "string" ? binding : String(binding.field || "")
        const row = source === "system" ? (runtimeModel.system || ({}))
            : source === "status" ? (runtimeModel.status || ({}))
            : source === "actions" ? (runtimeModel.actions || ({}))
            : item || view.selectedItem
        if (!row || !field) return ""
        const value = row[field]
        return value === undefined || value === null ? "" : value
    }

    function valueFor(element, item) {
        if (!element) return ""
        return view.bindingValue(element.binding, item)
    }

    function textFor(element, item, fallback) {
        if (!element) return fallback || ""
        if (element.text) return String(element.text)
        const value = view.valueFor(element, item)
        return value === "" || value === undefined ? (fallback || "") : String(value)
    }

    function mediaFor(item, role) {
        const row = item || view.selectedItem || ({})
        const order = role === "video" ? ["videoUrl", "heroUrl", "fanartUrl", "coverUrl"]
            : role === "background" ? ["heroUrl", "fanartUrl", "coverUrl", "bannerUrl"]
            : ["coverUrl", "artworkUrl", "bannerUrl"]
        for (let i = 0; i < order.length; ++i) {
            if (row[order[i]]) return String(row[order[i]])
        }
        return ""
    }

    function sourceFor(element, item, role) {
        if (element && element.source) return String(element.source)
        const value = view.valueFor(element, item)
        return value ? String(value) : view.mediaFor(item, role || "cover")
    }

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
        if (element.kind === "image") return !!view.sourceFor(element, view.selectedItem, "cover")
        if (element.kind === "text" || element.kind === "boundText")
            return !!(element.text || element.binding || view.selectedItem)
        if (element.kind === "video")
            return !!(view.sourceFor(element, view.selectedItem, "video") || view.selectedItem)
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
                    : (["image", "text", "boundText", "video"].indexOf(e.kind) === -1)
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

    function isFocusable(element) {
        if (!view.isDrawable(element)) return false
        if (element.selectable === false) return false
        // São os nós que representam conteúdo navegável do runtime. Imagens e
        // textos decorativos continuam fora da tabulação da cena.
        if (element.interactive === true) return true
        return ["carousel", "textList", "grid", "gameSelector"].indexOf(element.kind) !== -1
    }

    function geometryFor(element) {
        const lay = element && element.layout ? element.layout : ({})
        const fx = view.numberOr(lay, "x", 0)
        const fy = view.numberOr(lay, "y", 0)
        const fw = view.numberOr(lay, "width", 0)
        const fh = view.numberOr(lay, "height", 0)
        const width = fw > 0
            ? fw * view.width
            : (view.numberOr(lay, "maxWidth", 0) || view.numberOr(lay, "cropWidth", 0))
                * view.width
        const height = fh > 0
            ? fh * view.height
            : (view.numberOr(lay, "maxHeight", 0) || view.numberOr(lay, "cropHeight", 0))
                * view.height
        const ox = view.numberOr(lay, "xOrigin", 0)
        const oy = view.numberOr(lay, "yOrigin", 0)
        return {
            "x": fx * view.width - ox * width,
            "y": fy * view.height - oy * height,
            "width": width,
            "height": height
        }
    }

    function focusGeometry(element) {
        return view.geometryFor(element)
    }

    function resetFocus() {
        if (!view.interactive || view.focusableElements.length === 0) {
            view.currentFocusIndex = -1
            return
        }
        view.currentFocusIndex = 0
        view.forceActiveFocus()
        view.elementFocused(view.currentFocusId)
    }

    function focusCandidate(direction) {
        if (view.currentFocusIndex < 0 || view.currentFocusIndex >= view.focusableElements.length)
            return -1
        const current = view.geometryFor(view.focusableElements[view.currentFocusIndex])
        const cx = current.x + current.width / 2
        const cy = current.y + current.height / 2
        let best = -1
        let bestScore = Number.POSITIVE_INFINITY
        for (let i = 0; i < view.focusableElements.length; ++i) {
            if (i === view.currentFocusIndex) continue
            const candidate = view.geometryFor(view.focusableElements[i])
            const dx = candidate.x + candidate.width / 2 - cx
            const dy = candidate.y + candidate.height / 2 - cy
            let primary
            let secondary
            if (direction === "left" || direction === "right") {
                if (direction === "left" && dx >= 0) continue
                if (direction === "right" && dx <= 0) continue
                primary = Math.abs(dx)
                secondary = Math.abs(dy)
            } else {
                if (direction === "up" && dy >= 0) continue
                if (direction === "down" && dy <= 0) continue
                primary = Math.abs(dy)
                secondary = Math.abs(dx)
            }
            const score = primary * 1000 + secondary
            if (score < bestScore) {
                bestScore = score
                best = i
            }
        }
        return best
    }

    function moveFocus(direction) {
        if (!view.interactive || view.focusableElements.length === 0) return false
        if (view.currentFocusIndex < 0) {
            view.resetFocus()
            return true
        }
        // Um carrossel é um foco único com vários itens. Antes de procurar
        // outro nó geométrico, as setas horizontais percorrem a biblioteca;
        // sem isso a cena parecia navegável, mas o catálogo nunca mudava.
        if (["carousel", "gameSelector", "grid", "textList"].indexOf(
                view.focusedRuntimeKind()) !== -1
                && view.moveRuntimeItem(direction))
            return true
        const target = view.focusCandidate(direction)
        if (target < 0) return false
        view.currentFocusIndex = target
        view.forceActiveFocus()
        view.elementFocused(view.currentFocusId)
        return true
    }

    function activateCurrentFocus() {
        if (!view.interactive || view.currentFocusIndex < 0) return false
        view.elementActivated(view.currentFocusId)
        const item = view.selectedItem
        if (item && item.id !== undefined)
            view.itemActivated(String(item.id))
        return true
    }

    onInteractiveChanged: Qt.callLater(view.resetFocus)
    onRuntimeModelChanged: Qt.callLater(view.syncRuntimeSelection)
    Component.onCompleted: {
        view.syncRuntimeSelection()
        if (view.interactive) Qt.callLater(view.resetFocus)
    }

    focus: view.interactive
    activeFocusOnTab: view.interactive
    Accessible.name: qsTr("Cena do tema")

    Keys.onPressed: function(event) {
        if (!view.interactive) return
        let handled = true
        switch (event.key) {
        case Qt.Key_Left: handled = view.moveFocus("left"); break
        case Qt.Key_Right: handled = view.moveFocus("right"); break
        case Qt.Key_Up: handled = view.moveFocus("up"); break
        case Qt.Key_Down: handled = view.moveFocus("down"); break
        case Qt.Key_Return:
        case Qt.Key_Enter:
        case Qt.Key_Space: handled = view.activateCurrentFocus(); break
        default: handled = false
        }
        event.accepted = handled
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
                if (modelData.kind === "text" || modelData.kind === "boundText") return textComponent
                if (modelData.kind === "video") return videoComponent
                if (modelData.kind === "carousel") return carouselComponent
                if (modelData.kind === "rating") return ratingComponent
                if (modelData.kind === "badges") return badgesComponent
                if (modelData.kind === "systemStatus") return systemStatusComponent
                if (modelData.kind === "textList") return textListComponent
                if (modelData.kind === "grid") return gridComponent
                if (modelData.kind === "gameListInfo") return gameListInfoComponent
                if (modelData.kind === "gameSelector") return gameSelectorComponent
                return helpComponent
            }

            Component {
                id: imageComponent
                Item {
                    Image {
                        id: artwork
                        anchors.fill: parent
                        source: view.sourceFor(modelData, view.selectedItem, "cover")
                        // `tile` e o resto do IR pedem preenchimento distinto; sem
                        // isto um fundo 1x1 esticaria em vez de repetir.
                        fillMode: lay.tile === true ? Image.Tile : Image.PreserveAspectFit
                        asynchronous: true
                        cache: true
                        smooth: true
                        visible: source.toString().length > 0
                    }
                    Rectangle {
                        anchors.fill: parent
                        visible: !artwork.visible
                        color: view.highContrast ? "#000000" : "#172532"
                        border.color: view.highContrast ? "#ffffff" : view.esdeColor(app.textColor, "#5d7182")
                        border.width: view.highContrast ? 2 : 1
                        Text {
                            anchors.centerIn: parent
                            width: parent.width - 12
                            text: qsTr("Arte indisponível")
                            color: view.highContrast ? "#ffffff" : "#b8c7d2"
                            horizontalAlignment: Text.AlignHCenter
                            elide: Text.ElideRight
                        }
                    }
                }
            }


            // O carrossel é dirigido pelo catálogo real. Quando ele está vazio,
            // a mesma composição permanece legível com slots de fallback.
            Component {
                id: carouselComponent
                Item {
                    readonly property int declaredSlots: Math.max(
                        1, Math.min(12, Math.round(view.numberOr(lay, "maxItemCount", 3))))
                    readonly property int slots: view.runtimeItems.length > 0
                        ? Math.min(12, view.runtimeItems.length) : declaredSlots
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
                                required property int index
                                readonly property var item: view.runtimeItems.length > index
                                    ? view.runtimeItems[index] : ({})
                                width: slotW
                                height: slotH
                                radius: view.numberOr(lay, "imageCornerRadius", 0) * view.width
                                color: view.highContrast ? "#000000" : "#14212e"
                                border.color: view.esdeColor(app.textColor, "#3a4c5e")
                                border.width: index === view.activeItemIndex ? 2 : 1
                                opacity: index === view.activeItemIndex
                                    ? 1 : (view.reducedMotion ? 0.7 : 0.82)
                                scale: index === view.activeItemIndex
                                    ? (view.reducedMotion ? 1 : 1.04) : 1
                                Image {
                                    anchors.fill: parent
                                    anchors.margins: 2
                                    source: view.mediaFor(item, "cover")
                                    fillMode: Image.PreserveAspectFit
                                    asynchronous: true
                                    cache: true
                                    visible: source.toString().length > 0
                                }
                                Text {
                                    anchors.centerIn: parent
                                    width: parent.width - 10
                                    text: item.name || item.title || qsTr("Sem capa")
                                    visible: parent.children[0].visible === false
                                    color: view.esdeColor(app.textColor, "#9eabba")
                                    horizontalAlignment: Text.AlignHCenter
                                    elide: Text.ElideRight
                                    wrapMode: Text.Wrap
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

                    // Fanart/capa continuam visíveis quando QtMultimedia está
                    // ausente ou o vídeo está corrompido. O quadro de erro fica
                    // sobre a arte e explica o estado sem deixar tela preta.
                    Image {
                        anchors.fill: parent
                        source: view.mediaFor(view.selectedItem, "background")
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                        cache: true
                        visible: source.toString().length > 0 && !videoHost.multimediaReady
                        opacity: 0.72
                    }

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
                            item.clip = view.sourceFor(modelData, view.selectedItem, "video")
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
                        model: view.runtimeModel && Array.isArray(view.runtimeModel.actions)
                            && view.runtimeModel.actions.length > 0
                            ? view.runtimeModel.actions : [qsTr("Selecionar"), qsTr("Detalhes"), qsTr("Jogar")]
                        delegate: Row {
                            required property var modelData
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
                                text: String(modelData)
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
                    text: view.textFor(modelData, view.selectedItem,
                                       modelData.binding ? qsTr("Sem dados") : "")
                    color: view.highContrast ? "#ffffff" : view.esdeColor(app.color, "#e8eef6")
                    font.pixelSize: Math.max(10, view.numberOr(lay, "fontSize", 0.035)
                                                 * view.height)
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }
            }

            Component {
                id: ratingComponent
                Row {
                    spacing: 3
                    Text {
                        text: "★"
                        color: view.esdeColor(app.color, "#f4c542")
                        font.pixelSize: Math.max(12, view.numberOr(lay, "fontSize", 0.03) * view.height)
                    }
                    Text {
                        text: view.selectedItem.rating || view.selectedItem.score || qsTr("Sem avaliação")
                        color: view.highContrast ? "#ffffff" : view.esdeColor(app.textColor, "#e8eef6")
                        font.pixelSize: Math.max(10, view.numberOr(lay, "fontSize", 0.03) * view.height)
                    }
                }
            }

            Component {
                id: badgesComponent
                Row {
                    spacing: 6
                    Repeater {
                        model: view.selectedItem.badges && view.selectedItem.badges.length
                            ? view.selectedItem.badges : [qsTr("Sem selo")]
                        delegate: Rectangle {
                            required property var modelData
                            implicitWidth: badgeText.implicitWidth + 14
                            implicitHeight: badgeText.implicitHeight + 8
                            color: view.highContrast ? "#000000" : view.esdeColor(app.color, "#304354")
                            border.color: view.esdeColor(app.textColor, "#8aa1b4")
                            border.width: 1
                            radius: 4
                            Text {
                                id: badgeText
                                anchors.centerIn: parent
                                text: String(modelData)
                                color: "#ffffff"
                                font.pixelSize: Math.max(10, view.numberOr(lay, "fontSize", 0.02) * view.height)
                            }
                        }
                    }
                }
            }

            Component {
                id: systemStatusComponent
                Text {
                    text: view.runtimeModel.status && view.runtimeModel.status.label
                        ? String(view.runtimeModel.status.label) : qsTr("Estado indisponível")
                    color: view.highContrast ? "#ffffff" : view.esdeColor(app.textColor, "#e8eef6")
                    font.pixelSize: Math.max(10, view.numberOr(lay, "fontSize", 0.025) * view.height)
                    elide: Text.ElideRight
                }
            }

            Component {
                id: textListComponent
                Column {
                    spacing: 4
                    Repeater {
                        model: view.runtimeItems.length > 0 ? view.runtimeItems : [({})]
                        delegate: Text {
                            required property var modelData
                            text: modelData.name || modelData.title || qsTr("Sem título")
                            color: view.highContrast ? "#ffffff" : view.esdeColor(app.textColor, "#e8eef6")
                            font.pixelSize: Math.max(10, view.numberOr(lay, "fontSize", 0.025) * view.height)
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            Component {
                id: gridComponent
                Grid {
                    columns: Math.max(1, Math.round(view.numberOr(lay, "columns", 4)))
                    spacing: Math.max(4, view.numberOr(lay, "itemMarginX", 0.01) * view.width)
                    Repeater {
                        model: view.runtimeItems
                        delegate: Rectangle {
                            required property var modelData
                            width: view.numberOr(lay, "itemWidth", 0.12) * view.width
                            height: view.numberOr(lay, "itemHeight", 0.18) * view.height
                            color: view.highContrast ? "#000000" : "#172532"
                            border.color: view.esdeColor(app.textColor, "#5d7182")
                            Image {
                                anchors.fill: parent
                                anchors.margins: 2
                                source: view.mediaFor(modelData, "cover")
                                fillMode: Image.PreserveAspectFit
                                visible: source.toString().length > 0
                            }
                            Text {
                                anchors.centerIn: parent
                                text: modelData.name || modelData.title || qsTr("Sem capa")
                                visible: parent.children[0].visible === false
                                color: "#ffffff"
                                width: parent.width - 8
                                horizontalAlignment: Text.AlignHCenter
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }

            Component {
                id: gameListInfoComponent
                Column {
                    spacing: 5
                    Repeater {
                        model: [view.selectedItem.name || view.selectedItem.title || qsTr("Jogo sem título"),
                            view.selectedItem.genre || "", view.selectedItem.year || ""]
                        delegate: Text {
                            required property var modelData
                            visible: String(modelData).length > 0
                            text: String(modelData)
                            color: view.highContrast ? "#ffffff" : view.esdeColor(app.textColor, "#e8eef6")
                            font.pixelSize: Math.max(10, view.numberOr(lay, "fontSize", 0.025) * view.height)
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            Component {
                id: gameSelectorComponent
                Text {
                    text: view.selectedItem.name || view.selectedItem.title || qsTr("Selecione um jogo")
                    color: view.highContrast ? "#ffffff" : view.esdeColor(app.textColor, "#e8eef6")
                    font.pixelSize: Math.max(10, view.numberOr(lay, "fontSize", 0.03) * view.height)
                    elide: Text.ElideRight
                }
            }
        }
    }

    // O anel é um elemento da cena, não um overlay do painel. Assim a mesma
    // geometria declarada pelo tema continua governando o foco visível.
    SceneFocusRing {
        id: sceneFocusRing
        z: 100000
        model: {
            const element = view.focusableElements[view.currentFocusIndex]
            const rect = element ? view.focusGeometry(element) : ({})
            return {
                "id": element && element.id ? "focus-" + String(element.id) : "scene-focus-ring",
                "x": rect.x || 0,
                "y": rect.y || 0,
                "width": rect.width || 0,
                "height": rect.height || 0,
                "visible": view.interactive && !!element && (rect.width || 0) > 0
                    && (rect.height || 0) > 0,
                "color": view.focusColor,
                "borderWidth": 3
            }
        }
    }
}
