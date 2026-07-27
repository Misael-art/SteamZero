// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// A prova que faltava desde a regressão da a37: até aqui os testes comparavam
// strings de caminho ("../assets/eden.svg") e concluíam que o ícone existia.
// Caminho correto não é imagem renderizada. Este harness carrega cada asset
// empacotado de verdade e exige Image.Ready.
//
// Também exercita a allowlist: caminho arbitrário vindo de dado externo precisa
// ser recusado, e recusa precisa produzir fallback, não imagem quebrada.
import QtQuick
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 400
    height: 400

    property int failures: 0
    property int checks: 0
    property int pending: 0
    property bool loadPhaseDone: false

    readonly property var registry: PackagedAssets {}

    // Cobertura exigida explicitamente: Switch, os três emuladores Switch, cada
    // asset distinto das plataformas standalone, o RetroArch compartilhado e o
    // fallback de mídia de jogo.
    readonly property var requiredAssets: [
        "../assets/switch.svg",
        "../assets/eden.svg",
        "../assets/citron.svg",
        "../assets/ryubing.png",
        "../assets/playstation-2.svg",
        "../assets/playstation-portable.svg",
        "../assets/dreamcast.svg",
        "../assets/nintendo-ds.svg",
        "../assets/nintendo-3ds.svg",
        "../assets/wii-u.svg",
        "../assets/playstation-3.svg",
        "../assets/xbox.svg",
        "../assets/xbox-360.svg",
        "../assets/retroarch.svg",
        "../assets/steam.svg"
    ]

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        failures += 1
        console.error("FAIL: " + message)
    }

    Component {
        id: probeComponent
        Image {
            property string declared: ""
            visible: false
            asynchronous: false
            cache: false
        }
    }

    function probe(declared) {
        const resolved = harness.registry.resolve(declared)
        harness.check(String(resolved).length > 0,
                      "asset declarado precisa ser resolvível: " + declared)
        if (String(resolved).length === 0)
            return
        const image = probeComponent.createObject(harness, {"declared": declared})
        image.source = resolved
        // asynchronous: false garante decisão síncrona para SVG e PNG locais.
        harness.check(image.status === Image.Ready,
                      "asset precisa carregar (Image.Ready), status="
                      + image.status + " para " + declared)
        harness.check(image.implicitWidth > 0 && image.implicitHeight > 0,
                      "asset carregado precisa ter dimensão real: " + declared)
        image.destroy()
    }

    function runChecks() {
        // 1. Todo asset exigido pela emulação renderiza.
        for (let i = 0; i < requiredAssets.length; i++)
            probe(requiredAssets[i])

        // 2. Toda a allowlist renderiza — nenhum asset empacotado é decorativo.
        for (let j = 0; j < registry.allowed.length; j++)
            probe(registry.allowed[j])

        // 3. A allowlist recusa dado externo hostil.
        const rejected = [
            "../../../etc/passwd",
            "/etc/passwd",
            "file:///etc/passwd",
            "http://exemplo.invalido/x.svg",
            "qrc:/x.svg",
            "../assets/nao-existe.svg",
            "..",
            ""
        ]
        for (let k = 0; k < rejected.length; k++) {
            check(String(registry.resolve(rejected[k])).length === 0,
                  "caminho fora da allowlist precisa ser recusado: " + rejected[k])
        }

        // 4. Recusa é silenciosa e vazia, para o chamador aplicar fallback.
        check(registry.isAllowed("../assets/switch.svg"),
              "asset empacotado precisa ser aceito")
        check(!registry.isAllowed("../assets/inventado.svg"),
              "asset inexistente não pode ser aceito")

        // 5. O mesmo arquivo serve plataformas diferentes sem duplicar recurso.
        check(String(registry.resolve("../assets/retroarch.svg"))
              === String(registry.resolve("retroarch.svg")),
              "resolução precisa independer da forma como o caminho foi declarado")
    }

    Component.onCompleted: {
        runChecks()
        if (failures > 0) {
            console.error("FALHAS: " + failures + " de " + checks + " verificações")
            Qt.exit(1)
        } else {
            console.log("OK: " + checks + " verificações de asset")
            Qt.exit(0)
        }
    }
}
