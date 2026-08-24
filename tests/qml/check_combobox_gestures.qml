// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// ComboBox pela rota REAL do usuário. A sonda de controles só sabe clicar, e
// clicar num ComboBox não seleciona nada — por isso os cinco ComboBox
// habilitados da central ficavam `not-probed`. Emitir `activated()` na mão
// seria repetir o erro que este projeto já cometeu uma vez, quando `close()`
// fazia as vezes de Escape: prova o sinal, não a jornada.
//
// Aqui o evento é de teclado, entregue pelo QuickTest ao controle com foco.
// A raiz Item é intencional: QuickTest hospeda casos em QQuickView; Main é uma
// Window.

import QtQuick
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 1600
    height: 1000

    Main {
        id: shell
        visible: true
        width: 1600
        height: 1000
    }

    TestCase {
        id: suite
        name: "ComboBoxGestures"
        when: windowShown

        // Duck typing, como a sonda: o tipo concreto vem do estilo do host.
        function isComboBox(item) {
            return item.currentIndex !== undefined && item.model !== undefined
                && item.displayText !== undefined
        }

        // Coleta TODOS os ComboBox visíveis, habilitados ou não. O denominador
        // é o que existe na tela; separar depois é o que permite dizer "este foi
        // exercitado" e "este está bloqueado, e eis o motivo" sem esconder
        // nenhum dos dois.
        function collectComboBoxes(item, out) {
            if (!item)
                return out
            if (isComboBox(item) && item.visible)
                out.push(item)
            const kids = item.children || []
            for (let i = 0; i < kids.length; i++)
                collectComboBoxes(kids[i], out)
            return out
        }

        function exercisable(combo) {
            return combo.enabled && combo.count > 1
        }

        // Um ComboBox desabilitado não é defeito; desabilitado SEM motivo é.
        // Mesmo contrato que a matriz de controles cobra do resto da central.
        // Acumula em vez de parar no primeiro: um relatório que mostra só a
        // primeira acusação obriga a descobrir o resto uma rodada por vez.
        property var mute: []

        function noteIfMute(combo, label) {
            const reason = combo.Accessible.description || ""
            if (reason.length === 0)
                suite.mute.push(label + " ("
                                + (combo.Accessible.name || "sem nome acessível") + ")")
        }

        function showSection(sectionId) {
            // Sem janela ativa não há foco de teclado, e sem foco o keyClick não
            // chega a controle nenhum. Mesmo passo do harness de diálogos.
            shell.requestActivate()
            shell.sectionIndex = shell.sectionIndexOf(sectionId)
            tryVerify(function() {
                return shell.responsiveContent.currentIndex === shell.sectionIndex
            }, 4000, "seção " + sectionId + " não ficou ativa")
            return shell.responsiveContent.children[shell.sectionIndex]
        }

        // Um ComboBox exercitado de verdade muda de índice E avisa quem escuta.
        // Só o índice não basta: `currentIndex` muda por atribuição também, e
        // foi exatamente por isso que este controle nunca teve prova.
        function exerciseCombo(combo, label) {
            const before = combo.currentIndex
            let activatedIndex = -1
            function onActivated(index) { activatedIndex = index }
            combo.activated.connect(onActivated)

            combo.forceActiveFocus(Qt.TabFocusReason)
            // `activeFocusItem` do shell é a fonte confiável: `item.activeFocus`
            // depende de a janela estar ativa e engana offscreen.
            tryVerify(function() { return shell.activeFocusItem === combo }, 2000,
                      label + ": não recebeu foco para receber tecla")
            keyClick(before + 1 < combo.count ? Qt.Key_Down : Qt.Key_Up)

            const moved = combo.currentIndex !== before
            combo.activated.disconnect(onActivated)
            verify(moved, label + ": tecla real não mudou o índice (antes=" + before
                   + ", depois=" + combo.currentIndex + ")")
            verify(activatedIndex === combo.currentIndex,
                   label + ": mudou de índice sem emitir activated — quem escuta não soube ("
                   + activatedIndex + " != " + combo.currentIndex + ")")
        }

        // Percorre uma superfície e devolve o denominador fechado: cada
        // ComboBox visível ou foi exercitado por tecla real, ou está bloqueado
        // e diz por quê. Nenhum sai da conta em silêncio.
        function exerciseSurface(root, label) {
            const combos = collectComboBoxes(root, [])
            let exercised = 0
            let blocked = 0
            for (let i = 0; i < combos.length; i++) {
                const tag = label + "[" + i + "]"
                if (exercisable(combos[i])) {
                    exerciseCombo(combos[i], tag)
                    exercised += 1
                } else {
                    noteIfMute(combos[i], tag)
                    blocked += 1
                }
            }
            // Denominador no log: sem ele o verde não diz QUANTOS controles
            // foram cobertos, e um coletor que parasse de achar ComboBox
            // continuaria passando.
            console.log("COMBOBOX " + JSON.stringify({
                "surface": label, "visible": combos.length,
                "exercised": exercised, "blockedWithReason": blocked
            }))
            return combos.length
        }

        function exerciseSection(sectionId) {
            return exerciseSurface(showSection(sectionId), sectionId)
        }

        // A tela Steam mostra UMA área por vez, e as demais ficam invisíveis.
        // Percorrer só a área padrão deixava um ComboBox de fora do
        // denominador — e um denominador que não fecha é o defeito que esta
        // frente inteira está corrigindo.
        function test_01_steam_comboboxes_respond_to_real_keys() {
            const areas = ["performance", "controls", "library", "desktop"]
            let total = 0
            for (let i = 0; i < areas.length; i++) {
                shell.steamArea = areas[i]
                const root = showSection("steam")
                tryVerify(function() { return shell.steamArea === areas[i] }, 2000,
                          "área " + areas[i] + " não ficou ativa")
                total += exerciseSurface(root, "steam/" + areas[i])
            }
            verify(total > 0, "nenhum ComboBox encontrado na tela Steam")
            suite.verifyNoneAreMute()
        }

        function verifyNoneAreMute() {
            const offenders = suite.mute.slice()
            suite.mute = []
            verify(offenders.length === 0,
                   "ComboBox desabilitado sem motivo — nada diz ao usuário por quê:\n  "
                   + offenders.join("\n  "))
        }

        function test_02_profile_combobox_responds_to_real_keys() {
            verify(suite.exerciseSection("profiles") > 0)
            suite.verifyNoneAreMute()
        }

        function test_03_cast_combobox_responds_to_real_keys() {
            verify(suite.exerciseSection("cast") > 0)
            suite.verifyNoneAreMute()
        }
    }
}
