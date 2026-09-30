// SPDX-License-Identifier: GPL-3.0-or-later
// .pragma library: funções puras, sem estado e sem acesso aos objetos QML.
//
// UX-03 — leitura do contrato de prontidão v2 para qualquer superfície.
//
// Antes deste módulo, cada página decidia sozinha o que o número significava:
// `percent >= 80` pintava de verde uma categoria codificada (20/45/35/100), uma
// proporção real de requisitos e a simples existência de jogos inventariados, e
// um `percent` ausente virava 0%. O contrato separou estado, medição, causa e
// próxima ação; este módulo é a única tradução dessa separação para o QML, para
// que a regra não volte a ser reimplementada por página.
.pragma library

function _contrato(readiness) {
    return readiness && typeof readiness === "object" ? readiness : ({})
}

// Uma lista publicada pela bridge chega como QVariantList: `Array.isArray`
// responde false para ela, e o conteúdo continua íntegro (JSON com os itens,
// `length` numérico). Medido em sonda: `blockers` com dois itens,
// `Array.isArray(...) === false`. Um guard só em `Array.isArray` não é uma
// defesa — é um modo de falha silencioso, e foi assim que a caixa
// "Antes de continuar" ficou sem lista nenhuma na página montada por
// `createObject`, sem erro nem aviso.
function _lista(valor) {
    if (Array.isArray(valor))
        return valor
    if (valor && typeof valor === "object" && typeof valor.length === "number") {
        const copia = []
        for (let indice = 0; indice < valor.length; indice++)
            copia.push(valor[indice])
        return copia
    }
    return []
}

function contractVersion(readiness) {
    const value = Number(_contrato(readiness).contractVersion)
    return isNaN(value) ? 1 : value
}

function state(readiness) {
    const value = _contrato(readiness).state
    return typeof value === "string" && value.length > 0 ? value : "unverified"
}

function measure(readiness) {
    const value = _contrato(readiness).measure
    return value && typeof value === "object" ? value : null
}

// Uma medição só existe se vier dentro de `measure`, com percentual numérico.
// `readiness.percent` solto é o payload legado: número sem dimensão conhecida,
// que não pode ser exibido como se fosse uma proporção nem pintado como sucesso.
function percent(readiness) {
    const current = measure(readiness)
    if (!current)
        return null
    const value = current.percent
    return typeof value === "number" && isFinite(value) ? value : null
}

function isMeasured(readiness) {
    return percent(readiness) !== null
}

function showsProgress(readiness) {
    return isMeasured(readiness)
}

function progressValue(readiness) {
    const value = percent(readiness)
    return value === null ? 0 : Math.max(0, Math.min(100, value)) / 100
}

function percentText(readiness, missingText) {
    const value = percent(readiness)
    return value === null ? missingText : Math.round(value) + "%"
}

function ratioText(readiness) {
    const current = measure(readiness)
    if (!current)
        return ""
    const numerator = current.numerator
    const denominator = current.denominator
    if (typeof numerator !== "number" || typeof denominator !== "number")
        return ""
    return numerator + "/" + denominator
}

function dimensionText(readiness) {
    const current = measure(readiness)
    if (!current)
        return ""
    return typeof current.dimensionLabel === "string" ? current.dimensionLabel : ""
}

// A legenda da dimensão só acompanha um número que existe. Quando não há medição,
// `dimensionLabel` descreve a ausência (`not_measured`, `legacy_contract`) —
// mostrar isso na interface seria vazar uma chave do contrato.
function dimensionCaption(readiness) {
    return isMeasured(readiness) ? dimensionText(readiness) : ""
}

function absentReason(readiness) {
    const current = measure(readiness)
    if (!current || typeof current.absentReason !== "string")
        return ""
    return current.absentReason
}

function headline(readiness) {
    const current = _contrato(readiness)
    if (typeof current.label === "string" && current.label.length > 0)
        return current.label
    if (typeof current.title === "string" && current.title.length > 0)
        return current.title
    return ""
}

function cause(readiness) {
    const current = _contrato(readiness)
    if (typeof current.cause === "string" && current.cause.length > 0)
        return current.cause
    if (typeof current.detail === "string" && current.detail.length > 0)
        return current.detail
    return ""
}

function action(readiness) {
    const value = _contrato(readiness).nextAction
    return typeof value === "string" ? value : ""
}

function blockers(readiness) {
    return _lista(_contrato(readiness).blockers)
}

function verification(readiness) {
    const value = _contrato(readiness).verification
    return typeof value === "string" ? value : "unknown"
}

function basis(readiness) {
    const value = _contrato(readiness).basis
    return typeof value === "string" ? value : "none"
}

// Cor a partir do estado, nunca do número: 100% com um requisito ausente é
// bloqueio, e 67% medido com impedimento observado continua vermelho.
function tone(readiness) {
    const current = state(readiness)
    if (current === "ready")
        return "green"
    if (current === "blocked")
        return "red"
    if (current === "attention" || current === "degraded" || current === "unavailable")
        return "amber"
    return "muted"
}

function accent(readiness, colors) {
    if (!colors || typeof colors !== "object")
        return ""
    const key = tone(readiness)
    return colors[key] !== undefined ? colors[key] : colors.muted
}

// Fundo do cartão por tom. A página aplica a tinta do tema sobre ela; sem
// superfície definida (estado não observado) vale a cor neutra do tema, e um
// verde fixo diria "pronto" antes de qualquer leitura.
function surface(readiness) {
    const key = tone(readiness)
    if (key === "green")
        return "#0c2a21"
    if (key === "red")
        return "#2b1114"
    if (key === "amber")
        return "#24180b"
    return ""
}

// Fábrica do estado "ainda não observamos isto", no formato exato do contrato v2
// (`not_measured` + `absentReason`). Uma página sem backend, sem catálogo ou sem
// bridge precisa declarar esse estado; escrever o literal em cada uma era como
// ele divergia. Sem `state`, o cartão cairia em cinza mudo em vez de dizer por
// que não há número.
function notInspected(label, cause, nextAction, blockers) {
    return {
        "contractVersion": 2,
        "state": "unverified",
        "label": label,
        "cause": cause,
        "nextAction": nextAction === undefined ? null : nextAction,
        "blockers": blockers === undefined ? [] : blockers,
        "verification": "not_performed",
        "basis": "none",
        "pendingRequired": null,
        "pendingOptional": null,
        "measure": {
            "dimension": "not_measured",
            "dimensionLabel": "not_measured",
            "numerator": null,
            "denominator": null,
            "percent": null,
            "absentReason": "not_measured",
            "counts": {"satisfied": 0, "pending": 0, "unverified": 0, "notApplicable": 0}
        }
    }
}

// Uma linha ``{"percent": 45}`` pode chegar de uma store antiga em disco. Ela é
// lida sem exceção e o número fica invisível: sem dimensão conhecida, exibir 45%
// seria afirmar uma proporção que ninguém mediu.
function normalize(raw, fallback) {
    if (contractVersion(raw) >= 2)
        return raw
    const current = _contrato(raw)
    if (!(("percent" in current) || ("title" in current) || ("detail" in current)
            || ("blockers" in current)))
        return fallback
    return {
        "contractVersion": 2,
        "state": "unverified",
        "label": typeof current.title === "string" ? current.title : "",
        "cause": typeof current.detail === "string" ? current.detail : null,
        "nextAction": null,
        "blockers": _lista(current.blockers),
        "verification": "unknown",
        "basis": "none",
        "pendingRequired": null,
        "pendingOptional": null,
        "measure": {
            "dimension": "not_measured",
            "dimensionLabel": "not_measured",
            "numerator": null,
            "denominator": null,
            "percent": null,
            "absentReason": "legacy_contract",
            "counts": {"satisfied": 0, "pending": 0, "unverified": 0, "notApplicable": 0}
        }
    }
}
