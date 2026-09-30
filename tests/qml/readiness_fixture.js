// SPDX-License-Identifier: GPL-3.0-or-later
// .pragma library: utilitário de teste, não código de produção.
//
// Fixtures do contrato de prontidão v2 no formato exato que `readiness()` do
// domínio publica. Um harness que escreve `{"percent": 75}` à mão está testando
// a leitura de um payload legado, não a superfície real — e foi assim que a
// regra de cor do QML pôde divergir do contrato sem que ninguém percebesse.
.pragma library

function medido(estado, numerador, denominador, campos) {
    const atual = campos === undefined ? ({}) : campos
    const pendentes = denominador - numerador
    return {
        "contractVersion": 2,
        "state": estado,
        "label": atual.label === undefined ? "Prontidão sintética" : atual.label,
        "cause": atual.cause === undefined ? "Requisito ausente." : atual.cause,
        "nextAction": atual.action === undefined ? null : atual.action,
        "blockers": atual.blockers === undefined ? [] : atual.blockers,
        "verification": atual.verification === undefined ? "verified" : atual.verification,
        "basis": atual.basis === undefined ? "preflight" : atual.basis,
        "pendingRequired": atual.pendingRequired === undefined
            ? (pendentes > 0 ? pendentes : 0) : atual.pendingRequired,
        "pendingOptional": atual.pendingOptional === undefined ? 0 : atual.pendingOptional,
        "measure": {
            "dimension": "required_requirements",
            "dimensionLabel": atual.dimension === undefined
                ? "requisitos obrigatórios atendidos" : atual.dimension,
            "numerator": numerador,
            "denominator": denominador,
            "percent": denominador > 0 ? Math.round(100 * numerador / denominador) : null,
            "absentReason": null,
            "counts": {
                "satisfied": numerador, "pending": pendentes,
                "unverified": 0, "notApplicable": 0
            }
        }
    }
}

// Denominador zero: não existe proporção, e o contrato diz isso em vez de
// publicar 0% (falta) ou 100% (sucesso inventado).
function semMedicao(estado, campos) {
    const atual = campos === undefined ? ({}) : campos
    const payload = medido(estado, 0, 0, atual)
    payload.cause = atual.cause === undefined
        ? "Nenhum requisito em vigor foi observado neste escopo." : atual.cause
    payload.nextAction = atual.action === undefined ? null : atual.action
    payload.verification = atual.verification === undefined ? "not_performed" : atual.verification
    payload.basis = atual.basis === undefined ? "none" : atual.basis
    payload.pendingRequired = null
    payload.pendingOptional = null
    payload.measure.numerator = null
    payload.measure.denominator = null
    payload.measure.percent = null
    payload.measure.absentReason = "zero_denominator"
    payload.measure.counts = {
        "satisfied": 0, "pending": 0, "unverified": 0, "notApplicable": 2
    }
    return payload
}

// --- leitura de cor para as verificações de tinta --------------------------
// Utilitário de TESTE: o que se cobra daqui para frente é requisito visual, não
// o literal que a implementação escolheu. Um pino de cor exata prova que ninguém
// trocou um caractere — não prova que a cor comunica o estado, que as três são
// distinguíveis nem que continuam legíveis sobre a tinta clara do tema.
function canais(valor) {
    if (valor === undefined || valor === null)
        return null
    if (typeof valor === "object") {
        if (valor.r === undefined)
            return null
        return { "r": valor.r, "g": valor.g, "b": valor.b }
    }
    const texto = String(valor)
    if (texto.slice(0, 1) !== "#")
        return null
    let hex = texto.slice(1)
    if (hex.length === 3)
        hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2]
    if (hex.length !== 6)
        return null
    const numero = parseInt(hex, 16)
    if (isNaN(numero))
        return null
    return {
        "r": ((numero >> 16) & 255) / 255,
        "g": ((numero >> 8) & 255) / 255,
        "b": (numero & 255) / 255
    }
}

function minimo(canal) {
    return Math.min(canal.r, Math.min(canal.g, canal.b))
}

function luminancia(valor) {
    const c = canais(valor)
    if (c === null)
        return null
    function componente(v) {
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * componente(c.r) + 0.7152 * componente(c.g)
         + 0.0722 * componente(c.b)
}

// Razão de contraste WCAG 2.x, a mesma fórmula que as páginas usam para escolher
// a tinta sobre uma superfície.
function contraste(primeira, segunda) {
    const a = luminancia(primeira)
    const b = luminancia(segunda)
    if (a === null || b === null)
        return null
    const maior = Math.max(a, b)
    const menor = Math.min(a, b)
    return (maior + 0.05) / (menor + 0.05)
}
