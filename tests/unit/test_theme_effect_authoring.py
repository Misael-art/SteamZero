# SPDX-License-Identifier: GPL-3.0-or-later
"""V4 — pilha de efeitos: criar→editar→desfazer→salvar→reabrir→resolver no runtime."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.theme_editor import ThemeEditorManager

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "src" / "steamzero" / "schemas" / "theme-manifest-v1.schema.json").read_text("utf-8")
)


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
