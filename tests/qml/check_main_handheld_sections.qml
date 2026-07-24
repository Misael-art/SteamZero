// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Main {
    id: window
    visible: true
    width: 949
    height: 593

    property int failures: 0
    property int checks: 0
    property int firstFailure: 0
    property int phase: 0
    property int viewportIndex: 0
    readonly property var viewports: [
        {"width": 949, "height": 593},
        {"width": 1280, "height": 800}
    ]

    desktopStatus: ({
        "truthState": "ready",
        "desiredProfile": "handheld-desktop",
        "appliedProfile": "handheld-desktop",
        "observedProfile": "handheld-desktop",
        "recommendedProfile": "handheld-desktop",
        "statusReasons": [],
        "recoveryRequired": false,
        "independentRuntime": true,
        "context": {
            "deviceKind": "deck-lcd",
            "displays": [],
            "capabilities": [],
            "conflicts": []
        },
        "dashboard": {
            "accessibility": {"reducedMotion": true},
            "components": [],
            "steam": [],
            "sync": {
                "pending": 2,
                "conflicted": 1,
                "done": 4,
                "provider": {
                    "id": "fixture-provider",
                    "detail": "Provider sintético somente leitura"
                },
                "items": [{
                    "id": "fixture-item-0001",
                    "state": "conflicted",
                    "direction": "upload",
                    "gameId": "fixture-game",
                    "conflict": {"preserved": true}
                }],
                "dependency": "Fixture local; nenhuma mutação disponível."
            },
            "doctor": {"checks": []},
            "diagnostics": {"operations": {"items": [{
                "operationId": "01J0000000000000000000000A",
                "operation": "emulator.config",
                "kind": "emulator.config",
                "title": "Configuração de emulador",
                "state": "committed",
                "timestamp": "2026-07-23T12:00:00+00:00",
                "target": "arquivo:0123456789ab",
                "changeCount": 1,
                "rollbackAvailable": true,
                "rollback": {
                    "available": true,
                    "guarantee": "G-FULL",
                    "route": "transaction",
                    "reason": ""
                }
            }]}},
            "playtime": {
                "schemaVersion": 1,
                "totalPlayedSeconds": 3661,
                "games": [{
                    "gameId": "10",
                    "gameRef": "steam:10",
                    "title": "Fixture",
                    "source": "steam",
                    "favorite": true,
                    "playedSeconds": 3661,
                    "continueState": "interrupted",
                    "action": {
                        "kind": "steam-continue",
                        "target": "10",
                        "label": "Continuar",
                        "enabled": true,
                        "reason": ""
                    }
                }]
            },
            "collections": {
                "schemaVersion": 1,
                "favorites": ["steam:10"],
                "tags": [{"id": "coop", "name": "Co-op", "color": "#13BDF2"}],
                "collections": [{
                    "id": "favorites",
                    "name": "Favoritos",
                    "rule": {
                        "match": "all",
                        "predicates": [{"field": "favorite", "value": true}]
                    },
                    "members": ["steam:10"]
                }]
            },
            "libraryHealth": {
                "schemaVersion": 1,
                "state": "suspect",
                "counts": {
                    "verified": 3,
                    "suspect": 1,
                    "missing": 0,
                    "error": 0,
                    "unavailable": 0,
                    "unchecked": 2
                }
            },
            "uiContracts": {
                "schemaVersion": 1,
                "states": [],
                "actions": [],
                "byId": {}
            }
        }
    })

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        if (firstFailure === 0)
            firstFailure = checks
        failures += 1
        console.error("FAIL: " + message)
    }

    function checkScrollWidth(scroll, context) {
        check(scroll && scroll.contentItem,
              context + ": seção deve publicar Flickable")
        if (!scroll || !scroll.contentItem)
            return
        check(scroll.contentItem.contentWidth <= scroll.availableWidth + 1,
              context + ": seção não pode ter overflow horizontal")
    }

    function scrollControlAboveFooter(scroll, control, context) {
        checkScrollWidth(scroll, context)
        if (!scroll || !scroll.contentItem || !control)
            return
        control.forceActiveFocus(Qt.TabFocusReason)
        window.ensureFocusedItemVisible(control)
        const bottom = control.mapToItem(
            window.contentItem, 0, control.height).y
        const footerTop = window.responsiveFooter.mapToItem(
            window.contentItem, 0, 0).y
        check(bottom <= footerTop + 0.5,
              context + ": último controle deve ficar acima do rodapé")
    }

    function runPhase() {
        if (phase === 0) {
            check(window.compactLayout,
                  "viewport handheld deve usar shell compacto")
            check(window.reducedMotion && window.motionDuration === 0,
                  "shell deve zerar animações com movimento reduzido")
            check(window.bottomSafeInset >= 48,
                  "shell deve reservar margem inferior explícita")
            check(window.emulationControl.motionDuration === 0,
                  "Emulação deve herdar movimento reduzido do shell")
            check(window.steamGameplayControl.motionDuration === 0,
                  "Steam deve herdar movimento reduzido do shell")
            window.sectionIndex = 0
            phase = 1
            return
        }
        if (phase === 1) {
            checkScrollWidth(window.overviewScrollControl, "Visão geral")
            check(window.playtimeRepeaterControl.count === 1,
                  "Continuar jogando deve renderizar a sessão recente")
            check(window.playtimeRepeaterControl.itemAt(0).height >= 48,
                  "Continuar jogando deve manter alvo 48×48")
            window.sectionIndex = 3
            phase = 2
            return
        }
        if (phase === 2) {
            check(window.profilePickerControl.height >= 48,
                  "seletor de perfil deve manter alvo 48×48")
            check(window.profilePlanControl.height >= 48,
                  "revisão de perfil deve manter alvo 48×48")
            scrollControlAboveFooter(
                window.profilesScrollControl,
                window.profilePlanControl,
                "Perfis")
            window.sectionIndex = 4
            phase = 3
            return
        }
        if (phase === 3) {
            check(window.syncProviderControl.visible,
                  "provider de Sync deve permanecer visível")
            check(window.syncProviderControl.width
                  <= window.syncScrollControl.availableWidth + 0.5,
                  "provider de Sync não pode ser cortado horizontalmente")
            check(window.syncUpdateControl.height >= 48,
                  "Atualizar Sync deve manter alvo 48×48")
            scrollControlAboveFooter(
                window.syncScrollControl,
                window.syncUpdateControl,
                "Saves e Sync")
            window.syncUpdateControl.forceActiveFocus(Qt.TabFocusReason)
            window.diagnosticsPreview = {
                "files": ["fixture.json"],
                "content": {"readOnly": true}
            }
            window.diagnosticsPreviewControl.open()
            phase = 4
            return
        }
        if (phase === 4) {
            check(window.diagnosticsPreviewControl.visible,
                  "diálogo somente leitura deve abrir no handheld")
            window.diagnosticsPreviewControl.close()
            phase = 5
            return
        }
        if (phase === 5) {
            check(window.activeFocusItem === window.syncUpdateControl,
                  "fechar diálogo deve devolver foco ao invocador")
            window.sectionIndex = 5
            phase = 6
            return
        }
        if (phase === 6) {
            checkScrollWidth(window.systemScrollControl, "Sistema")
            window.operationRollbackPlan = {
                "planId": "01J0000000000000000000000B",
                "confirmToken": "fixture-confirm-token",
                "operationId": "01J0000000000000000000000A",
                "kind": "emulator.config",
                "title": "Configuração de emulador",
                "target": "arquivo:0123456789ab",
                "changeCount": 1,
                "rollbackGuarantee": "G-FULL"
            }
            window.operationRollbackControl.open()
            phase = 7
            return
        }
        if (phase === 7) {
            check(window.operationRollbackControl.visible,
                  "preview de rollback contextual deve abrir no handheld")
            check(window.operationRollbackControl.width <= window.width - 48 + 0.5,
                  "preview de rollback não pode exceder o viewport")
            window.operationRollbackControl.close()
            window.collectionManagerControl.open()
            phase = 8
            return
        }
        if (phase === 8) {
            check(window.collectionManagerControl.visible,
                  "gerenciador de coleções deve abrir no handheld")
            check(window.collectionManagerControl.width <= window.width - 48 + 0.5,
                  "gerenciador de coleções não pode exceder o viewport")
            window.collectionManagerControl.close()
            window.libraryHealthPlan = {
                "planId": "01J0000000000000000000000C",
                "confirmToken": "fixture-health-token",
                "preview": "Amostragem limitada e somente leitura."
            }
            window.libraryHealthPlanControl.open()
            phase = 9
            return
        }
        if (phase === 9) {
            check(window.libraryHealthPlanControl.visible,
                  "preview anti-bitrot deve abrir no handheld")
            check(window.libraryHealthPlanControl.width <= window.width - 48 + 0.5,
                  "preview anti-bitrot não pode exceder o viewport")
            window.libraryHealthPlanControl.close()
            viewportIndex += 1
            if (viewportIndex >= viewports.length) {
                Qt.exit(failures === 0 ? 0 : firstFailure)
                return
            }
            const viewport = viewports[viewportIndex]
            width = viewport.width
            height = viewport.height
            sectionIndex = 0
            phase = 0
        }
    }

    Timer {
        interval: 40
        running: true
        repeat: true
        onTriggered: window.runPhase()
    }
}
