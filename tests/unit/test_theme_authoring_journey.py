# SPDX-License-Identifier: GPL-3.0-or-later
"""V3 — jornada de autoria: criar, editar, desfazer/refazer, salvar, reabrir,
exportar e importar como cópia, com o resultado resolvido pelo mesmo resolver
que o runtime usa."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import jsonschema
import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.media_recipes import MediaRecipe, parse_media_recipes, resolve_fit
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


def _recipe(preview: dict[str, object], role: str) -> dict[str, object]:
    recipes = preview["mediaRecipes"]
    assert isinstance(recipes, dict)
    return dict(recipes[role])


def test_edit_undo_redo_keeps_document_and_preview_in_step(env: Path) -> None:
    mgr = ThemeEditorManager()
    created = mgr.create("Jornada")
    sid = str(created["sessionId"])
    base = _recipe(created["preview"], "focusedCover")  # type: ignore[arg-type]
    assert base["fit"] == "contain"  # herdado do tema padrão

    first = mgr.set_media_recipe(sid, "focusedCover", "fit", "cover")
    second = mgr.set_media_recipe(sid, "focusedCover", "orientation", "auto")
    assert first["history"]["undoDepth"] == 1
    assert second["history"]["undoDepth"] == 2
    assert _recipe(second["preview"], "focusedCover")["orientation"] == "auto"  # type: ignore[arg-type]

    undone = mgr.undo(sid)
    assert "orientation" not in _recipe(undone["preview"], "focusedCover")  # type: ignore[arg-type]
    assert undone["manifest"]["mediaRecipes"]["recipes"]["focusedCover"]["fit"] == "cover"  # type: ignore[index]
    assert undone["history"]["canRedo"] is True

    redone = mgr.redo(sid)
    assert _recipe(redone["preview"], "focusedCover")["orientation"] == "auto"  # type: ignore[arg-type]

    mgr.undo(sid)
    mgr.undo(sid)
    back = mgr.preview(sid)["preview"]
    assert _recipe(back, "focusedCover") == base  # type: ignore[arg-type]
    with pytest.raises(SteamZeroError, match="nada para desfazer"):
        mgr.undo(sid)


def test_new_edit_after_undo_discards_redo_and_invalid_edit_leaves_history(env: Path) -> None:
    mgr = ThemeEditorManager()
    sid = str(mgr.create("Redo")["sessionId"])
    mgr.set_media_recipe(sid, "focusedCover", "fit", "cover")
    mgr.undo(sid)
    state = mgr.set_media_recipe(sid, "focusedCover", "alignH", "left")["history"]
    assert state["canRedo"] is False and state["undoDepth"] == 1
    with pytest.raises(SteamZeroError):
        mgr.set_media_recipe(sid, "focusedCover", "fit", "esticar")
    with pytest.raises(SteamZeroError):
        mgr.set_media_recipe(sid, "focusedCover", "focalX", 7)
    with pytest.raises(SteamZeroError):
        mgr.set_media_recipe(sid, "focusedCover", "sourceOrder", ["cover"])
    assert mgr.history(sid)["history"]["undoDepth"] == 1


def test_save_reopen_export_import_copy_roundtrip(env: Path) -> None:
    mgr = ThemeEditorManager()
    created = mgr.create("Ciclo completo")
    sid = str(created["sessionId"])
    theme_id = str(created["manifest"]["id"])  # type: ignore[index]
    mgr.set_media_recipe(sid, "focusedCover", "fit", "contain")
    mgr.set_media_recipe(sid, "focusedCover", "orientation", "landscape")
    mgr.set_media_recipe(sid, "focusedCover", "alignV", "top")
    mgr.set_media_recipe(sid, "focusedCover", "focalX", 0.9)
    expected = _recipe(mgr.preview(sid)["preview"], "focusedCover")  # type: ignore[arg-type]
    mgr.save(sid)

    # Reabre numa sessão nova: nada vem da memória da anterior.
    reopened = ThemeEditorManager().load(theme_id)
    assert _recipe(reopened["preview"], "focusedCover") == expected  # type: ignore[arg-type]
    saved = json.loads(
        (env / "data" / "steamzero" / "themes" / theme_id / "theme.json").read_text()
    )
    jsonschema.validate(saved, SCHEMA)
    assert parse_media_recipes(saved["mediaRecipes"])["focusedCover"].align_v.value == "top"  # type: ignore[union-attr]

    package = env / "ciclo.zip"
    package.write_bytes(mgr.export_zip(sid))
    with zipfile.ZipFile(package) as z:
        assert f"{theme_id}/theme.json" in z.namelist()
        assert not any(n.lower().endswith((".png", ".jpg")) for n in z.namelist()), (
            "renderize, não edite: a receita não gera cópias pré-transformadas"
        )

    from steamzero.adapters.desktop_dashboard import DesktopDashboard

    dashboard = DesktopDashboard()
    with pytest.raises(SteamZeroError):  # mesmo id sem confirmação: original intacto
        dashboard.theme_import_zip_apply(str(package))
    before = (env / "data" / "steamzero" / "themes" / theme_id / "theme.json").read_bytes()
    with pytest.raises(SteamZeroError):
        dashboard.theme_import_zip_apply(str(package), overwrite=True, as_copy=True)
    result = dashboard.theme_import_zip_apply(str(package), as_copy=True)
    copy_id = str(result.get("id") or result.get("themeId"))
    assert copy_id != theme_id and copy_id.startswith(theme_id)
    assert (env / "data" / "steamzero" / "themes" / theme_id / "theme.json").read_bytes() == before

    copy_loaded = ThemeEditorManager().load(copy_id)
    assert _recipe(copy_loaded["preview"], "focusedCover") == expected  # type: ignore[arg-type]
    assert copy_loaded["manifest"]["name"].endswith("(cópia)")  # type: ignore[index]


@pytest.mark.parametrize(
    ("orientation", "image", "slot", "fit"),
    [
        ("none", (600, 900), (900, 600), "contain"),
        ("auto", (900, 600), (600, 900), "contain"),  # paisagem em slot retrato: sem recorte
        ("auto", (600, 900), (600, 900), "crop"),
        ("auto", (500, 500), (600, 900), "crop"),  # quadrada nunca força recuo
        ("portrait", (900, 600), (600, 900), "contain"),
        ("portrait", (600, 900), (900, 600), "crop"),
        ("landscape", (600, 900), (900, 600), "contain"),
    ],
)
def test_resolve_fit_is_deterministic_and_explained(orientation, image, slot, fit) -> None:  # type: ignore[no-untyped-def]
    declared = "contain" if orientation == "none" else "crop"
    recipe = MediaRecipe.from_dict(
        "focusedCover",
        {"sourceOrder": ["cover"], "fit": declared, "orientation": orientation},
    )
    first = resolve_fit(recipe, *image, *slot)
    assert first == resolve_fit(recipe, *image, *slot)
    assert first["fit"] == fit
    assert first["reason"]


def test_focal_point_and_explicit_alignment() -> None:
    recipe = MediaRecipe.from_dict(
        "focusedCover", {"sourceOrder": ["cover"], "focalX": 0.9, "focalY": 0.1}
    )
    out = resolve_fit(recipe, 600, 900, 600, 900)
    assert (out["alignH"], out["alignV"]) == ("right", "top")
    explicit = MediaRecipe.from_dict(
        "focusedCover",
        {"sourceOrder": ["cover"], "focalX": 0.9, "alignH": "left"},
    )
    assert resolve_fit(explicit, 1, 1, 1, 1)["alignH"] == "left"


def test_edited_theme_reaches_runtime_resolver_and_apply_names_consumer(env: Path) -> None:
    """Tema editado→salvo→resolvido pelo catálogo (o mesmo caminho do runtime) →
    plano de aplicação explícito que nomeia o consumidor."""
    from steamzero.adapters.desktop_dashboard import DesktopDashboard
    from steamzero.adapters.theme_catalog import ThemeCatalog
    from steamzero.core import paths

    mgr = ThemeEditorManager()
    created = mgr.create("Runtime")
    sid = str(created["sessionId"])
    theme_id = str(created["manifest"]["id"])  # type: ignore[index]
    mgr.set_media_recipe(sid, "focusedCover", "fit", "contain")
    mgr.set_media_recipe(sid, "focusedCover", "orientation", "auto")
    mgr.set_media_recipe(sid, "focusedCover", "alignV", "top")
    mgr.save(sid)

    resolved = ThemeCatalog(user_themes_dir=paths.themes_dir()).resolve(theme_id)
    runtime = resolved.to_theme_qml_object()
    assert runtime["themeId"] == theme_id, "o runtime não pode cair no builtin"
    recipe = runtime["mediaRecipes"]["focusedCover"]
    assert (recipe["fit"], recipe["orientation"], recipe["alignV"]) == ("contain", "auto", "top")
    # Capa retrato num slot paisagem: o contrato decide sem recortar e explica.
    decision = resolve_fit(MediaRecipe.from_dict("focusedCover", recipe), 600, 900, 900, 600)
    assert decision["fit"] == "contain" and decision["alignV"] == "top"

    plan = DesktopDashboard().plan_theme_apply(theme_id)
    assert plan["status"] == "ready" and plan["consumer"] == "central"
    assert "Launcher" in plan["scope"]
