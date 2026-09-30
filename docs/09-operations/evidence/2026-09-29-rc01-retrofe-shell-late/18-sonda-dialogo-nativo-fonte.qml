// SPDX-License-Identifier: GPL-3.0-or-later
// Sonda descartável (fora da árvore): o FileDialog abre e é dirigível sob offscreen
// dentro do MESMO mecanismo que o gate usa (qmltestrunner)?
import QtQuick
import QtTest
import QtQuick.Dialogs

TestCase {
    id: sonda
    name: "ProbeFileDialog"
    when: windowShown

    FileDialog {
        id: dlg
        objectName: "probeFileDialog"
        title: "Sonda"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Layouts RetroFE (*.xml)", "Todos os arquivos (*)"]
        onAccepted: console.log("SONDA aceitou " + (dlg.selectedFile || ""))
        onRejected: console.log("SONDA rejeitou")
    }

    function varre(nivel, profundidade) {
        if (!nivel || profundidade > 7)
            return
        const kids = nivel.children || []
        for (let i = 0; i < kids.length; i++) {
            const f = kids[i]
            if (f.objectName)
                console.log("SONDA NO " + "  ".repeat(profundidade) + f.objectName
                            + " :: tipo=" + (f.toString ? String(f).split("@")[0] : "?")
                            + " :: texto=" + (f.text !== undefined ? JSON.stringify(f.text) : "-")
                            + " :: visivel=" + (f.visible === true))
            varre(f, profundidade + 1)
        }
    }

    function test_01_abrir() {
        console.log("SONDA antes: visivel=" + dlg.visible + " contentItem=" + (dlg.contentItem ? "sim" : "nao"))
        dlg.open()
        wait(1200)
        console.log("SONDA depois: visivel=" + dlg.visible + " contentItem=" + (dlg.contentItem ? "sim" : "nao"))
        varre(dlg.contentItem, 0)
        console.log("SONDA fim do teste 01")
    }
}
