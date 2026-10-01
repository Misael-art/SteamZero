// SPDX-License-Identifier: GPL-3.0-or-later
// .pragma library: funções puras. Espelho de ``media_recipes.resolve_fit``
// (Python); tests/integration/test_media_fit_parity.py exige resultado idêntico.
.pragma library

function _shape(w, h) {
    if (!(w > 0) || !(h > 0))
        return "unknown"
    if (Math.abs(w - h) / Math.max(w, h) < 0.02)
        return "square"
    return w > h ? "landscape" : "portrait"
}

function _anchor(focal, low, high) {
    return focal < 1 / 3 ? low : (focal > 2 / 3 ? high : "center")
}

function resolve(recipe, imageW, imageH, slotW, slotH) {
    const r = recipe || ({})
    const rawFit = r.fit || "crop"
    const declared = (rawFit === "crop" || rawFit === "cover") ? "crop" : rawFit
    const image = _shape(imageW, imageH)
    const slot = _shape(slotW, slotH)
    const orientation = r.orientation || "none"
    let fit = declared
    let reason = "fit declarado: " + declared
    const oriented = function(s) { return s === "portrait" || s === "landscape" }
    if (orientation === "auto") {
        if (oriented(image) && oriented(slot) && image !== slot) {
            fit = "contain"
            reason = "auto: imagem " + image + " em slot " + slot + "; sem recorte"
        } else {
            reason = "auto: imagem " + image + " e slot " + slot + " compatíveis; " + declared
        }
    } else if (orientation !== "none") {
        if (oriented(image) && image !== orientation) {
            fit = "contain"
            reason = orientation + " esperado, imagem " + image + "; sem recorte"
        } else {
            reason = orientation + " esperado e atendido; " + declared
        }
    }
    const fx = r.focalX === undefined ? 0.5 : r.focalX
    const fy = r.focalY === undefined ? 0.5 : r.focalY
    return {
        "fit": fit,
        "alignH": r.alignH || _anchor(fx, "left", "right"),
        "alignV": r.alignV || _anchor(fy, "top", "bottom"),
        "reason": reason
    }
}
