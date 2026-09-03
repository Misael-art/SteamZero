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
        return ["x", "y", "width", "height", "maxWidth", "maxHeight"]
            .some(function(key) { return Number(lay[key]) > 0 })
    }

    function isDrawable(element) {
        if (!view.hasGeometry(element)) return false
        if (element.kind === "image") return !!element.source
        if (element.kind === "text") return !!(element.text || element.binding)
        return false
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
                : (e.kind !== "image" && e.kind !== "text")
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
                : view.numberOr(lay, "maxWidth", 0) * view.width
            readonly property real ph: fh > 0
                ? fh * view.height
                : view.numberOr(lay, "maxHeight", 0) * view.height

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
                return modelData.kind === "image" ? imageComponent : textComponent
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
