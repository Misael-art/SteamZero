// SPDX-License-Identifier: GPL-3.0-or-later
// .pragma library: funções puras, sem estado e sem acesso aos objetos QML.
//
// UX-04 — grandeza de armazenamento em unidade compreensível e localizada.
//
// Quatro páginas formatavam bytes cada uma do seu jeito: duas em KiB/MiB/GiB,
// uma com rótulo decimal (`GB`/`MB`) sobre divisor 1024 — que afirma um valor
// ~7% menor que o medido — e uma parando em MB, onde 1 TiB sai como
// `1048576.0 MB`. O mesmo número tinha quatro leituras. Este módulo é a única
// tradução, para que a escolha de unidade não volte a morar por página.
//
// Dois fatos do runtime, medidos no Qt 6.11.2 do projeto antes de escrever o
// formatador (sondas `probe_qt_formatbytesize.qml` e
// `probe_qt_localized_number.qml`):
//
// 1. Não existe formatador de bytes exposto ao QML aqui — `Qt.formatByteSize`,
//    `QLocale.formatByteSize` e `QLocale.formatDataSize` respondem "is not a
//    function". A escolha de unidade tem de ser própria.
// 2. `Number(v).toLocaleString(Qt.locale())` é a única formatação localizada
//    disponível: produz `1.430,50` com separador decimal do locale. Ele exige o
//    argumento de locale (sem ele, `1048576` saiu como `1,04858e+06` — nota
//    científica), rejeita objeto de opções e sempre imprime duas casas
//    decimais. Por isso o número acima de 1 KiB delega ao locale e a faixa de
//    bytes, que é inteira por construção, usa inteiro sem separador.
.pragma library

var ABSENTE = "—"

var _unidades = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB"]

// Grandeza ausente não é zero: é "não medido", e tem representação própria.
function _ausente(valor) {
    if (valor === null || valor === undefined)
        return true
    const bytes = Number(valor)
    return !isFinite(bytes) || bytes < 0
}

function bytes(valor) {
    if (_ausente(valor))
        return ABSENTE
    const total = Number(valor)
    if (total < 1024)
        return total.toFixed(0) + " " + _unidades[0]
    let expoente = 1
    while (expoente < _unidades.length - 1 && total >= Math.pow(1024, expoente + 1))
        expoente += 1
    // Duas casas em qualquer andar: a precisão não pode saltar de 1 para 2
    // dentro da mesma tela, e o locale já decide o separador.
    return (total / Math.pow(1024, expoente)).toLocaleString(Qt.locale()) + " " + _unidades[expoente]
}
