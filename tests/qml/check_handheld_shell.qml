// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Main {
    id: window
    visible: true
    property int failures: 0

    function check(condition, message) {
        if (condition)
            return
        failures += 1
        console.error("FAIL: " + message)
    }

    function verifyViewport(expectedWidth, expectedHeight) {
        check(width === expectedWidth && height === expectedHeight,
              "viewport deve manter a dimensão solicitada")
        check(compactLayout, "viewport handheld deve usar o shell compacto")
        check(responsiveHeader.visible, "cabeçalho compacto deve permanecer visível")
        check(responsiveHeader.height >= 48, "cabeçalho precisa acomodar controles de 48 px")
        check(responsiveFooter.visible && responsiveFooter.height >= 44,
              "rodapé handheld deve permanecer reservado")
        const contentBottom = responsiveContent.mapToItem(
            window.contentItem, 0, responsiveContent.height).y
        const footerTop = responsiveFooter.mapToItem(window.contentItem, 0, 0).y
        check(contentBottom <= footerTop + 0.5,
              "conteúdo não pode ficar sob o rodapé")
    }

    function runChecks() {
        width = 949
        height = 593
        verifyViewport(949, 593)
        check(minimumWidth <= 949 && minimumHeight <= 593,
              "mínimos não podem bloquear a resolução lógica handheld")
        check(motionDuration >= 160 && motionDuration <= 220,
              "movimento deve respeitar a faixa reduzida")
        check(responsiveDrawer.width <= width * 0.82 + 0.5,
              "drawer não pode cobrir toda a tela")
        check(responsiveDrawerNavigation.count === 6,
              "drawer deve publicar todas as áreas principais")
        check(responsiveTaskDrawer.width <= width * 0.94 + 0.5,
              "central de tarefas deve respeitar a largura handheld")
        liveTasks = [{
            "jobId": "job-1", "type": "library.scan", "state": "running",
            "progress": {"current": 1, "total": 4}, "result": null,
            "canCancel": true, "canRetry": false, "errorCode": null
        }]
        check(activeTaskCount() === 1, "tarefa ativa deve aparecer no indicador global")
        check(taskProgress(liveTasks[0]) === 0.25, "progresso deve usar medição publicada")
        const emulationItem = responsiveDrawerNavigation.itemAt(1)
        const steamItem = responsiveDrawerNavigation.itemAt(2)
        check(emulationItem.KeyNavigation.down === steamItem,
              "D-pad deve avançar entre os destinos do drawer")
        sectionIndex = 2
        steamArea = "controls"
        check(sectionIndex === 2 && steamArea === "controls",
              "navegação deve preservar seção e subárea")
        width = 1280
        height = 800
        verifyViewport(1280, 800)
        Qt.exit(failures === 0 ? 0 : 1)
    }

    Timer { interval: 100; running: true; onTriggered: window.runChecks() }
}
