// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Resolução allowlisted dos assets empacotados.
//
// Motivo: manifests de plataforma e de emulador declaram caminhos como
// "../assets/switch.svg". Esse valor é DADO EXTERNO — chega de JSON e atravessa
// o backend até virar Image.source. Entregá-lo cru ao Image significa aceitar
// qualquer caminho ou URL que um manifesto contenha.
//
// Aqui o caminho declarado é reduzido ao nome do arquivo, conferido contra a
// lista de assets efetivamente empacotados e só então resolvido com
// Qt.resolvedUrl(), que funciona tanto em árvore fonte quanto em wheel
// instalado. Nome fora da lista devolve string vazia, e o chamador aplica o
// fallback iconográfico.
//
// A lista abaixo é verificada por tests/unit/test_packaged_assets.py, que exige
// igualdade com os arquivos reais de src/steamzero/ui/assets e com tudo que os
// manifests referenciam. Acrescentar asset sem atualizar os dois lados reprova.
import QtQuick

QtObject {
    id: registry

    readonly property var allowed: [
        "amazon-luna.svg",
        "arcade.svg",
        "azahar.svg",
        "cemu.png",
        "citron.svg",
        "dolphin-emu.svg",
        "dreamcast.svg",
        "duckstation.svg",
        "eden.svg",
        "flycast.png",
        "geforce-now.svg",
        "mega-drive.svg",
        "melonds.svg",
        "nes-famicom.svg",
        "nintendo-3ds.svg",
        "nintendo-console.svg",
        "nintendo-ds.svg",
        "nintendo-handheld.svg",
        "pcsx2.png",
        "playstation-2.svg",
        "playstation-3.svg",
        "playstation-portable.svg",
        "playstation-vita.svg",
        "playstation.svg",
        "ppsspp.svg",
        "retroarch.svg",
        "rpcs3.png",
        "ryubing.png",
        "snes.svg",
        "steam.svg",
        "steamzero-mark.png",
        "sunshine.svg",
        "switch.svg",
        "vita3k.svg",
        "wii-u.svg",
        "xbox-360.svg",
        "xbox-cloud-gaming.svg",
        "xbox.svg",
        "xemu.svg",
        "xenia.png"
    ]

    // Aceita "../assets/x.svg", "assets/x.svg" ou "x.svg"; recusa o resto.
    function resolve(declared) {
        const raw = String(declared || "")
        if (raw.length === 0)
            return ""
        // Qualquer esquema (file:, http:, qrc:) é dado externo tentando escolher
        // a origem do recurso: recusa antes de olhar o nome.
        if (raw.indexOf(":") >= 0)
            return ""
        const name = raw.substring(raw.lastIndexOf("/") + 1)
        if (name.length === 0 || name === "." || name === "..")
            return ""
        if (registry.allowed.indexOf(name) < 0)
            return ""
        return Qt.resolvedUrl("../assets/" + name)
    }

    function isAllowed(declared) {
        return registry.resolve(declared).toString().length > 0
    }
}
