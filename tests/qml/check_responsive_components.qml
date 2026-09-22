// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Componentes reutilizáveis precisam consumir a escala visual quando são
// hospedados por uma superfície acessível. Este harness verifica o contrato
// diretamente nos componentes, sem depender de pixels de uma tela específica.
import QtQuick
import QtQuick.Controls
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    id: window
    width: 960
    height: 640

    Flickable {
        id: scrollArea
        width: 520
        height: 260
        contentWidth: width
        contentHeight: 960
        Item { id: firstAnchor; y: 0 }
        Item { id: secondAnchor; y: 380 }
    }

    SectionNavigator {
        id: navigator
        flickable: scrollArea
        sections: [
            {"label": "Primeira", "item": firstAnchor},
            {"label": "Segunda", "item": secondAnchor}
        ]
        visualScale: 1.5
    }

    SectionMenu {
        id: sectionMenu
        sections: [{"label": "Primeira"}, {"label": "Segunda"}]
        visualScale: 1.5
    }

    LoadingOverlay {
        id: loadingOverlay
        active: true
        visualScale: 1.5
    }

    EmptyState {
        id: emptyState
        visualScale: 1.5
    }

    FeedbackNotice {
        id: feedbackNotice
        width: 520
        message: "Falha controlada"
        error: true
        visualScale: 1.5
    }

    TestCase {
        name: "ResponsiveReusableComponents"
        when: true

        function test_navigator_scales_fixed_text() {
            compare(navigator.menuPixelSize, 30)
            compare(navigator.statusPixelSize, 17)
        }

        function test_section_menu_scales_title() {
            compare(sectionMenu.titlePixelSize, 30)
        }

        function test_loading_overlay_scales_text() {
            compare(loadingOverlay.titlePixelSize, 32)
            compare(loadingOverlay.detailPixelSize, 18)
        }

        function test_empty_state_scales_title() {
            compare(emptyState.titlePixelSize, 30)
        }

        function test_feedback_notice_scales_impact() {
            compare(feedbackNotice.impactPixelSize, 18)
        }
    }
}
