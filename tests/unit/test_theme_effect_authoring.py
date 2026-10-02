# SPDX-License-Identifier: GPL-3.0-or-later
"""V4 — pilha de efeitos: criar→editar→desfazer→salvar→reabrir→resolver no runtime."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.scene_motion import motion_editor_schema
from steamzero.domain.theme_editor import ThemeEditorManager
from steamzero.domain.theme_effects import effect_editor_schema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "src" / "steamzero" / "schemas" / "theme-manifest-v1.schema.json").read_text("utf-8")
)


def test_editor_schema_exposes_closed_fields_and_domain_ranges() -> None:
    schema = effect_editor_schema()
    assert schema["shadow"]["parameters"]["color"]["kind"] == "color"
    radius = schema["shadow"]["parameters"]["blur"]
    assert radius == {
        "kind": "number",
        "default": 12.0,
        "minimum": 0,
        "maximum": 48,
        "step": 1.0,
        "decimals": 2,
    }
    assert schema["shadow"]["fallbacks"] == ["omit", "minimal"]

    created = ThemeEditorManager().create("Schema de edição")
    assert created["effectSchema"] == schema


def test_motion_editor_schema_exposes_native_states_and_ranges() -> None:
    schema = motion_editor_schema()
    assert {"loading", "error", "offline", "playing"} <= set(schema["states"])
    assert schema["timelineKinds"] == ["sequence", "parallel"]
    assert schema["keyframes"]["scale"] == {
        "minimum": 0.5,
        "maximum": 2.0,
        "step": 0.05,
        "decimals": 2,
    }
    assert schema["duration"] == {"minimum": 0, "maximum": 2000, "step": 1}
    assert schema["repeat"] == {"minimum": 0, "maximum": 8, "step": 1}
    assert ThemeEditorManager().create("Schema de movimento")["motionSchema"] == schema


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    return tmp_path


def _stack(preview: dict[str, object], name: str) -> list[dict[str, object]]:
    effects = preview["effects"]
    assert isinstance(effects, dict)
    return [dict(e) for e in effects.get(name, [])]


def test_effect_edit_undo_redo_save_reopen_and_runtime(env: Path) -> None:
    mgr = ThemeEditorManager()
    created = mgr.create("Efeitos")
    sid = str(created["sessionId"])
    theme_id = str(created["manifest"]["id"])  # type: ignore[index]

    added = mgr.edit_effect_stack(sid, "focusedCover", "add", effect_type="glow")
    assert added["history"]["undoDepth"] == 1  # type: ignore[index]
    n = len(added["stack"])  # type: ignore[arg-type]
    index = n - 1
    edited = mgr.edit_effect_stack(
        sid, "focusedCover", "set", index=index, param="strength", value=0.8
    )
    assert edited["stack"][index]["strength"] == 0.8  # type: ignore[index]
    seen = _stack(edited["preview"], "focusedCover")  # type: ignore[arg-type]
    assert seen[index]["parameters"]["strength"] == 0.8

    undone = mgr.undo(sid)
    assert _stack(undone["preview"], "focusedCover")[index]["parameters"]["strength"] == 0.25  # type: ignore[arg-type]
    mgr.redo(sid)
    expected = _stack(mgr.preview(sid)["preview"], "focusedCover")  # type: ignore[arg-type]
    mgr.save(sid)

    reopened = ThemeEditorManager().load(theme_id)
    assert _stack(reopened["preview"], "focusedCover") == expected  # type: ignore[arg-type]
    saved = json.loads(
        (env / "data" / "steamzero" / "themes" / theme_id / "theme.json").read_text()
    )
    jsonschema.validate(saved, SCHEMA)

    # Runtime: mesmo resolver, com movimento reduzido/alto contraste degradando o efeito.
    plain = mgr.preview(sid, reduced_motion=True)["preview"]
    assert _stack(plain, "focusedCover")  # glow não é movimento: permanece
    contrast = mgr.preview(sid, high_contrast=True)["preview"]
    assert _stack(contrast, "focusedCover") == []  # omitido p/ legibilidade, sem derrubar a cena


def test_effect_edit_move_remove_and_invalid_edits_keep_document(env: Path) -> None:
    mgr = ThemeEditorManager()
    sid = str(mgr.create("Efeitos 2")["sessionId"])
    mgr.edit_effect_stack(sid, "s", "add", effect_type="blur")
    mgr.edit_effect_stack(sid, "s", "add", effect_type="vignette")
    moved = mgr.edit_effect_stack(sid, "s", "move", index=1, value=0)
    assert [e["type"] for e in moved["stack"]] == ["vignette", "blur"]  # type: ignore[union-attr]
    depth = mgr.history(sid)["history"]["undoDepth"]  # type: ignore[index]
    for kwargs in (
        {"op": "add", "effect_type": "shader"},  # fora da allowlist
        {"op": "set", "index": 1, "param": "radius", "value": 9999},  # limite
        {"op": "set", "index": 1, "param": "codigo", "value": 1},  # parâmetro desconhecido
        {"op": "set", "index": 5, "param": "radius", "value": 1},
        {"op": "remove", "index": 9},
        {"op": "explode"},
    ):
        op = str(kwargs.pop("op"))
        with pytest.raises(SteamZeroError):
            mgr.edit_effect_stack(sid, "s", op, **kwargs)  # type: ignore[arg-type]
    assert mgr.history(sid)["history"]["undoDepth"] == depth  # type: ignore[index]
    removed = mgr.edit_effect_stack(sid, "s", "remove", index=0)
    assert [e["type"] for e in removed["stack"]] == ["blur"]  # type: ignore[union-attr]


def _motion(preview: dict[str, object]) -> dict[str, object]:
    motion = preview["sceneMotionPreview"]
    assert isinstance(motion, dict)
    return motion


def test_motion_timeline_edit_undo_save_reopen_and_resolve(env: Path) -> None:
    mgr = ThemeEditorManager()
    created = mgr.create("Movimento")
    sid = str(created["sessionId"])
    theme_id = str(created["manifest"]["id"])  # type: ignore[index]

    mgr.edit_motion(sid, "set_state", timeline="focused", field="scale", value=1.2)
    mgr.edit_motion(sid, "add_timeline", timeline="entrada", value="sequence")
    mgr.edit_motion(
        sid, "add_clip", timeline="entrada", value={"state": "focused", "duration": 240}
    )
    edited = mgr.edit_motion(
        sid, "set_clip", timeline="entrada", index=1, field="duration", value=300
    )
    assert edited["motion"]["timelines"]["entrada"]["clips"][1]["duration"] == 300  # type: ignore[index]
    mgr.edit_motion(sid, "set_timeline", timeline="entrada", field="repeat", value=2)
    assert mgr.history(sid)["history"]["undoDepth"] == 5  # type: ignore[index]

    undone = mgr.undo(sid)
    assert undone["manifest"]["sceneMotion"]["timelines"]["entrada"]["repeat"] == 0  # type: ignore[index]
    mgr.redo(sid)
    expected = mgr.preview(sid)["preview"]
    mgr.save(sid)

    reopened = ThemeEditorManager().load(theme_id)
    assert _motion(reopened["preview"]) == _motion(expected)  # type: ignore[arg-type]
    saved = json.loads(
        (env / "data" / "steamzero" / "themes" / theme_id / "theme.json").read_text()
    )
    motion_schema = json.loads(
        (ROOT / "src" / "steamzero" / "schemas" / "scene-motion-v1.schema.json").read_text("utf-8")
    )
    jsonschema.validate(saved["sceneMotion"], motion_schema)
    timeline = _motion(expected)["timelines"]["entrada"]  # type: ignore[index]
    assert [c["duration"] for c in timeline["steps"]] == [0, 300]  # type: ignore[index]


def test_motion_invalid_edits_keep_document(env: Path) -> None:
    mgr = ThemeEditorManager()
    sid = str(mgr.create("Movimento 2")["sessionId"])
    mgr.edit_motion(sid, "add_timeline", timeline="t", value="parallel")
    depth = mgr.history(sid)["history"]["undoDepth"]  # type: ignore[index]
    for kwargs in (
        {"op": "set_state", "timeline": "focused", "field": "scale", "value": 9},
        {"op": "set_state", "timeline": "inventado", "field": "scale", "value": 1},
        {"op": "add_timeline", "timeline": "t", "value": "sequence"},
        {"op": "add_timeline", "timeline": "Inválido!", "value": "sequence"},
        {"op": "set_clip", "timeline": "t", "index": 0, "field": "duration", "value": 99999},
        {"op": "remove_clip", "timeline": "t", "index": 0},  # timeline não pode ficar vazia
        {"op": "add_clip", "timeline": "t", "value": {"transition": "ausente"}},
        {"op": "remove_timeline", "timeline": "nao-existe"},
    ):
        op = str(kwargs.pop("op"))
        with pytest.raises(SteamZeroError):
            mgr.edit_motion(sid, op, **kwargs)  # type: ignore[arg-type]
    assert mgr.history(sid)["history"]["undoDepth"] == depth  # type: ignore[index]


def test_motion_clips_reorder_and_invalid_targets_are_atomic(env: Path) -> None:
    mgr = ThemeEditorManager()
    sid = str(mgr.create("Ordem de clips")["sessionId"])
    mgr.edit_motion(sid, "add_timeline", timeline="entrada", value="parallel")
    mgr.edit_motion(
        sid, "add_clip", timeline="entrada", value={"state": "focused", "duration": 240}
    )
    mgr.edit_motion(
        sid, "add_clip", timeline="entrada", value={"state": "loading", "duration": 300}
    )

    moved = mgr.edit_motion(sid, "move_clip", timeline="entrada", index=2, value=0)
    clips = moved["motion"]["timelines"]["entrada"]["clips"]  # type: ignore[index]
    assert [clip["state"] for clip in clips] == ["loading", "normal", "focused"]
    depth = mgr.history(sid)["history"]["undoDepth"]  # type: ignore[index]
    before = moved["motion"]
    for kwargs in (
        {"index": 0, "value": -1},
        {"index": 0, "value": 3},
        {"index": 3, "value": 1},
        {"index": 0, "value": 1.5},
        {"index": 0, "value": True},
    ):
        with pytest.raises(SteamZeroError):
            mgr.edit_motion(sid, "move_clip", timeline="entrada", **kwargs)
    current = mgr._get_session(sid).manifest["sceneMotion"]
    assert current == before
    assert mgr.history(sid)["history"]["undoDepth"] == depth  # type: ignore[index]


def test_first_edit_keeps_inherited_motion_and_declared_effects_survive_negotiation(
    env: Path,
) -> None:
    mgr = ThemeEditorManager()
    parent = ThemeEditorManager().load("org.steamzero.asset-recipes-demo")
    inherited = parent["declared"]["sceneMotion"]  # type: ignore[index]
    assert inherited and inherited["timelines"], "o demo precisa declarar timelines"

    sid = str(mgr.create("Herdeiro", extends="org.steamzero.asset-recipes-demo")["sessionId"])
    edited = mgr.edit_motion(sid, "set_state", timeline="focused", field="scale", value=1.1)
    kept = edited["declared"]["sceneMotion"]  # type: ignore[index]
    assert set(inherited["timelines"]) <= set(kept["timelines"]), (
        "a primeira edição perdeu timelines"
    )
    assert kept["states"]["focused"]["scale"] == 1.1

    mgr.edit_effect_stack(sid, "focusedCover", "add", effect_type="glow")
    declared = _declared_stack(mgr, sid)
    assert any(e["type"] == "glow" for e in declared)
    # O preview negociado (alto contraste) omite efeitos; a declaração do documento não.
    contrast = mgr.preview(sid, high_contrast=True)["preview"]
    assert _stack(contrast, "focusedCover") == []  # type: ignore[arg-type]
    assert any(e["type"] == "glow" for e in _declared_stack(mgr, sid))


def _declared_stack(mgr: ThemeEditorManager, sid: str) -> list[dict[str, object]]:
    state = mgr.edit_effect_stack(sid, "focusedCover", "move", index=0, value=0)
    return [dict(e) for e in state["declared"]["effects"]["focusedCover"]]  # type: ignore[index]


def test_export_import_copy_preserves_effects_and_motion_semantics(env: Path) -> None:
    from steamzero.adapters.desktop_dashboard import DesktopDashboard

    mgr = ThemeEditorManager()
    created = mgr.create("Roundtrip V4")
    sid = str(created["sessionId"])
    theme_id = str(created["manifest"]["id"])  # type: ignore[index]
    mgr.edit_effect_stack(sid, "focusedCover", "add", effect_type="shadow")
    mgr.edit_effect_stack(sid, "focusedCover", "set", index=2, param="blur", value=20)
    mgr.edit_motion(sid, "set_state", timeline="focused", field="opacity", value=0.8)
    mgr.edit_motion(sid, "add_timeline", timeline="entrada", value="parallel")
    mgr.edit_motion(sid, "set_timeline", timeline="entrada", field="repeat", value=2)
    mgr.set_media_recipe(sid, "focusedCover", "fit", "cover")
    mgr.save(sid)
    original = ThemeEditorManager().load(theme_id)

    package = env / "roundtrip.zip"
    package.write_bytes(mgr.export_zip(sid))
    result = DesktopDashboard().theme_import_zip_apply(str(package), as_copy=True)
    copy_id = str(result.get("id") or result.get("themeId"))
    assert copy_id != theme_id
    copy = ThemeEditorManager().load(copy_id)

    # Mesma semântica de documento; id/nome/namespace da cópia podem diferir.
    for key in ("effects", "sceneMotion", "mediaRecipes"):
        assert copy["manifest"].get(key) == original["manifest"].get(key), key  # type: ignore[union-attr]
    assert copy["declared"] == original["declared"]
    assert _stack(copy["preview"], "focusedCover") == _stack(original["preview"], "focusedCover")  # type: ignore[arg-type]
    assert (
        ThemeEditorManager().load(theme_id)["manifest"] == original["manifest"]
    )  # original intacto


def test_binding_edit_inherits_layouts_validates_allowlist_and_roundtrips(env: Path) -> None:
    mgr = ThemeEditorManager()
    created = mgr.create("Binding", extends="org.steamzero.asset-recipes-demo")
    sid = str(created["sessionId"])
    theme_id = str(created["manifest"]["id"])  # type: ignore[index]
    inherited = created["declared"]["sceneLayouts"]["layouts"]  # type: ignore[index]
    assert "previewTitles" in inherited, "o layout herdado deve aparecer na declaração"

    edited = mgr.edit_layout_binding(
        sid, "previewTitles", "text", binding="item.genre", fallback="Sem gênero"
    )
    assert edited["layout"]["template"]["properties"]["text"] == {  # type: ignore[index]
        "binding": "item.genre",
        "fallback": "Sem gênero",
    }
    assert set(inherited) <= set(edited["declared"]["sceneLayouts"]["layouts"])  # type: ignore[index]
    depth = mgr.history(sid)["history"]["undoDepth"]  # type: ignore[index]
    for bad in ("item.senha", "item.", "layout.title", "item.title; rm -rf /"):
        with pytest.raises(SteamZeroError):
            mgr.edit_layout_binding(sid, "previewTitles", "text", binding=bad)
    with pytest.raises(SteamZeroError):  # propriedade fora do template
        mgr.edit_layout_binding(sid, "previewTitles", "script", binding="item.title")
    assert mgr.history(sid)["history"]["undoDepth"] == depth

    undone = mgr.undo(sid)
    assert (
        undone["declared"]["sceneLayouts"]["layouts"]["previewTitles"]["template"]["properties"][  # type: ignore[index]
            "text"
        ]["binding"]
        == "item.title"
    )
    mgr.redo(sid)
    cleared = mgr.edit_layout_binding(sid, "previewTitles", "text", binding=None, fallback="Fixo")
    assert cleared["layout"]["template"]["properties"]["text"] == "Fixo"  # type: ignore[index]
    mgr.undo(sid)
    mgr.save(sid)
    reopened = ThemeEditorManager().load(theme_id)
    reopened_props = reopened["declared"]["sceneLayouts"]["layouts"]["previewTitles"]["template"][  # type: ignore[index]
        "properties"
    ]
    assert reopened_props["text"]["binding"] == "item.genre"
