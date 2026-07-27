from __future__ import annotations

import contextlib
import json
import tempfile
from pathlib import Path

import jsonschema
import pytest

from steamzero.adapters.theme_catalog import (
    ThemeCatalog,
    list_builtin_theme_ids,
    read_builtin_manifest,
    validate_theme_directory,
)
from steamzero.core.errors import SteamZeroError
from steamzero.domain.themes import (
    MAX_EXTENDS_DEPTH,
    THEME_API_VERSION,
    THEME_DEFAULT_ID,
    ResolvedTheme,
    ThemeColorTokens,
    ThemeGeometryTokens,
    ThemeManifest,
    ThemeMotionTokens,
    ThemeResolver,
    ThemeTypographyTokens,
)

_SCHEMA_DIR = Path(__file__).parents[2] / "src" / "steamzero" / "schemas"


def _load_schema(name: str) -> dict:
    return json.loads((_SCHEMA_DIR / name).read_text(encoding="utf-8"))


_MK = dict[str, str | int | dict]  # helper: partial manifest
_VALID = {
    "schemaVersion": 1,
    "kind": "steamzero-theme-v1",
    "id": "org.steamzero.default",
    "name": "TestDefault",
    "version": "1.0.0",
    "author": "SZ",
    "license": "GPL-3.0-or-later",
    "compatibility": {"themeApi": 1},
    "tokens": {"color": {"background": "#000000"}},
}


def _man(id_: str = "a.b", **kw: object) -> dict:
    base = {
        "schemaVersion": 1,
        "kind": "steamzero-theme-v1",
        "id": id_,
        "name": "X",
        "version": "1.0.0",
        "author": "X",
        "license": "MIT",
        "compatibility": {"themeApi": 1},
    }
    base.update(kw)
    return base


@pytest.mark.parametrize(
    "desc,manifest,expect",
    [
        ("schema version errada", _man(schemaVersion=2), "schemaVersion"),
        ("kind errado", _man(kind="steamzero-theme-v2"), "kind"),
        ("id inválido", _man(id="Invalid_ID!"), "id"),
        ("SemVer inválido", _man(version="1.0"), "version"),
        ("chave extra", _man(extraKey=True), "extraKey"),
        ("cor inválida", _man(tokens={"color": {"background": "nope"}}), "background"),
        ("api incompatível", _man(compatibility={"themeApi": 2}), "themeApi"),
        ("licença inválida", _man(license=""), "license"),
    ],
)
def test_manifest_schema_rejects_invalid(desc: str, manifest: dict, expect: str) -> None:
    schema = _load_schema("theme-manifest-v1.schema.json")
    with pytest.raises(jsonschema.ValidationError) as exc:
        jsonschema.validate(manifest, schema)
    assert expect in str(exc.value)


def test_valid_manifest_accepts() -> None:
    schema = _load_schema("theme-manifest-v1.schema.json")
    jsonschema.validate(_VALID, schema)


def test_schema_additional_properties_false() -> None:
    schema = _load_schema("theme-manifest-v1.schema.json")
    assert schema.get("additionalProperties") is False


def test_schema_empacotado() -> None:
    assert _SCHEMA_DIR.joinpath("theme-manifest-v1.schema.json").exists()


def test_preference_schema_valid() -> None:
    schema = _load_schema("theme-preference-v1.schema.json")
    jsonschema.validate({"schemaVersion": 1, "themeId": "a.b", "themeVersion": "1.0.0"}, schema)


def test_preference_schema_rejects_extra() -> None:
    schema = _load_schema("theme-preference-v1.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"schemaVersion": 1, "themeId": "a.b", "themeVersion": "1.0.0", "extra": True}, schema
        )


def test_default_theme_id() -> None:
    assert THEME_DEFAULT_ID == "org.steamzero.default"


def test_theme_api_version() -> None:
    assert THEME_API_VERSION == 1


def test_manifest_roundtrip() -> None:
    m = ThemeManifest(id="org.t.t", name="T", version="1.2.3", author="Tester")
    r = ThemeManifest.from_dict(m.to_dict())
    assert r.id == "org.t.t"
    assert r.name == "T"
    assert r.version == "1.2.3"


def test_color_defaults() -> None:
    c = ThemeColorTokens()
    assert c.background == "#071019"
    assert c.text == "#f2f6fb"
    assert len(c.to_dict()) == 18


def test_geometry_defaults() -> None:
    g = ThemeGeometryTokens()
    assert g.minimumTarget == 48


def test_typography_defaults() -> None:
    t = ThemeTypographyTokens(scale=1.25)
    assert t.scale == 1.25


def test_motion_defaults() -> None:
    m = ThemeMotionTokens()
    assert m.durationFast == 120


def test_resolved_theme_to_dict() -> None:
    rt = ResolvedTheme(
        id="a.b", name="T", version="1.0.0", author="X", license="MIT", description=""
    )
    d = rt.to_dict()
    assert d["id"] == "a.b"
    assert "tokens" in d


def test_resolved_theme_qml_object() -> None:
    rt = ResolvedTheme(
        id="a.b", name="T", version="1.0.0", author="X", license="MIT", description=""
    )
    obj = rt.to_theme_qml_object()
    assert obj["schemaVersion"] == 1
    assert obj["themeId"] == "a.b"
    assert "resolved" in obj


def test_high_contrast_override() -> None:
    rt = ResolvedTheme(
        id="a.b", name="T", version="1.0.0", author="X", license="MIT", description=""
    )
    hc = rt.apply_accessibility(high_contrast=True, reduced_motion=False)
    assert hc.color.background == "#000000"


def test_reduced_motion_override() -> None:
    rt = ResolvedTheme(
        id="a.b", name="T", version="1.0.0", author="X", license="MIT", description=""
    )
    rm = rt.apply_accessibility(high_contrast=False, reduced_motion=True)
    assert rm.motion.durationFast == 0


def test_both_accessibility() -> None:
    rt = ResolvedTheme(
        id="a.b", name="T", version="1.0.0", author="X", license="MIT", description=""
    )
    both = rt.apply_accessibility(high_contrast=True, reduced_motion=True)
    assert both.color.background == "#000000"
    assert both.motion.durationFast == 0


class TestResolution:
    def test_resolve_default(self) -> None:
        m = {
            THEME_DEFAULT_ID: ThemeManifest(
                id=THEME_DEFAULT_ID,
                name="Default",
                version="1.0.0",
                author="SZ",
                license="GPL-3.0-or-later",
            )
        }
        r = ThemeResolver(m).resolve(THEME_DEFAULT_ID)
        assert r.id == THEME_DEFAULT_ID
        assert r.color.background == "#071019"

    def test_resolve_extends(self) -> None:
        m = {
            THEME_DEFAULT_ID: ThemeManifest(
                id=THEME_DEFAULT_ID,
                name="Default",
                version="1.0.0",
                author="SZ",
                license="GPL-3.0-or-later",
            ),
            "org.t.child": ThemeManifest(
                id="org.t.child",
                name="Child",
                version="1.0.0",
                author="T",
                license="MIT",
                extends=THEME_DEFAULT_ID,
                tokens={"color": {"accent": "#ff0000"}},
            ),
        }
        r = ThemeResolver(m).resolve("org.t.child")
        assert r.color.accent == "#ff0000"
        assert r.color.background == "#071019"

    def test_cycle_detected(self) -> None:
        m = {
            "a.a": ThemeManifest(
                id="a.a", name="A", version="1.0.0", author="X", license="MIT", extends="b.b"
            ),
            "b.b": ThemeManifest(
                id="b.b", name="B", version="1.0.0", author="X", license="MIT", extends="a.a"
            ),
        }
        with pytest.raises(ValueError, match="ciclo"):
            ThemeResolver(m).resolve("a.a")

    def test_deep_chain_refused(self) -> None:
        manifests: dict[str, ThemeManifest] = {}
        for i in range(MAX_EXTENDS_DEPTH + 3):
            t = f"x.{i}"
            e = f"x.{i - 1}" if i > 0 else None
            manifests[t] = ThemeManifest(
                id=t, name=str(i), version="1.0.0", author="X", license="MIT", extends=e
            )
        with pytest.raises(ValueError, match="profundidade"):
            ThemeResolver(manifests).resolve(f"x.{MAX_EXTENDS_DEPTH + 2}")

    def test_missing_base(self) -> None:
        m = {
            "org.t.o": ThemeManifest(
                id="org.t.o",
                name="O",
                version="1.0.0",
                author="X",
                license="MIT",
                extends="org.missing.base",
            ),
        }
        with pytest.raises(ValueError, match="não encontrado"):
            ThemeResolver(m).resolve("org.t.o")

    def test_merge_chain_replaces(self) -> None:
        m = {
            THEME_DEFAULT_ID: ThemeManifest(
                id=THEME_DEFAULT_ID,
                name="Default",
                version="1.0.0",
                author="SZ",
                license="GPL-3.0-or-later",
                tokens={"color": {"background": "#000000", "accent": "#ffffff"}},
            ),
            "org.t.m": ThemeManifest(
                id="org.t.m",
                name="M",
                version="1.0.0",
                author="X",
                license="MIT",
                extends=THEME_DEFAULT_ID,
                tokens={"color": {"accent": "#ff0000"}},
            ),
        }
        r = ThemeResolver(m).resolve("org.t.m")
        assert r.color.background == "#000000"
        assert r.color.accent == "#ff0000"

    def test_nonexistent(self) -> None:
        m = {
            THEME_DEFAULT_ID: ThemeManifest(
                id=THEME_DEFAULT_ID,
                name="Default",
                version="1.0.0",
                author="SZ",
                license="GPL-3.0-or-later",
            )
        }
        with pytest.raises(ValueError, match="não encontrado"):
            ThemeResolver(m).resolve("org.nonexistent")


class TestBuiltinThemes:
    """WI-T1: temas builtin empacotados."""

    def test_list_builtins(self) -> None:
        ids = list_builtin_theme_ids()
        assert THEME_DEFAULT_ID in ids

    def test_default_builtin_reads(self) -> None:
        manifest = read_builtin_manifest(THEME_DEFAULT_ID)
        assert manifest.id == THEME_DEFAULT_ID
        assert manifest.version == "1.0.0"
        assert manifest.name == "SteamZero"

    def test_second_builtin_exists(self) -> None:
        ids = list_builtin_theme_ids()
        assert "org.steamzero.steamdeck" in ids

    def test_second_builtin_reads(self) -> None:
        manifest = read_builtin_manifest("org.steamzero.steamdeck")
        assert manifest.id == "org.steamzero.steamdeck"
        assert manifest.extends == THEME_DEFAULT_ID

    def test_catalog_lists_builtins(self) -> None:
        catalog = ThemeCatalog()
        entries = catalog.list_catalog()
        ids = [e["id"] for e in entries]
        assert THEME_DEFAULT_ID in ids
        assert "org.steamzero.steamdeck" in ids

    def test_default_builtin_is_always_available(self) -> None:
        catalog = ThemeCatalog()
        entries = catalog.list_catalog()
        default = next(e for e in entries if e["id"] == THEME_DEFAULT_ID)
        assert default["state"] == "available"

    def test_resolve_default_from_catalog(self) -> None:
        catalog = ThemeCatalog()
        resolved = catalog.resolve(THEME_DEFAULT_ID)
        assert resolved.id == THEME_DEFAULT_ID
        assert resolved.color.background == "#071019"


class TestUserThemeValidation:
    """WI-T2: validação de pacote local e segurança."""

    @pytest.fixture
    def tmp_theme(self) -> Path:
        d = Path(tempfile.mkdtemp())
        theme_dir = d / "org.test.valid"
        theme_dir.mkdir(parents=True)
        (theme_dir / "theme.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "kind": "steamzero-theme-v1",
                    "id": "org.test.valid",
                    "name": "Valid",
                    "version": "1.0.0",
                    "author": "Tester",
                    "license": "MIT",
                    "compatibility": {"themeApi": 1},
                    "tokens": {"color": {"background": "#ff0000"}},
                }
            )
        )
        (theme_dir / "assets").mkdir()
        yield theme_dir
        import shutil

        shutil.rmtree(d, ignore_errors=True)

    def test_valid_user_theme(self, tmp_theme: Path) -> None:
        manifest = validate_theme_directory(tmp_theme)
        assert manifest.id == "org.test.valid"
        assert manifest.author == "Tester"

    def test_catalog_lists_user_theme(self, tmp_theme: Path) -> None:
        catalog = ThemeCatalog(user_themes_dir=tmp_theme.parent)
        entries = catalog.list_catalog()
        ids = [e["id"] for e in entries]
        assert "org.test.valid" in ids

    def test_missing_manifest_rejected(self, tmp_theme: Path) -> None:
        (tmp_theme / "theme.json").unlink()
        with pytest.raises(SteamZeroError, match=r"theme\.json"):
            validate_theme_directory(tmp_theme)

    def test_symlink_rejected(self, tmp_theme: Path) -> None:
        link = tmp_theme / "evil.link"
        link.symlink_to("/etc/passwd")
        with pytest.raises(SteamZeroError):
            validate_theme_directory(tmp_theme)

    def test_outside_root_rejected(self, tmp_theme: Path) -> None:
        outside = tmp_theme.parent.parent / "outside.txt"
        outside.write_text("outside")
        link = tmp_theme / "ref"
        with contextlib.suppress(OSError):
            link.symlink_to(outside)
        with pytest.raises(SteamZeroError):
            validate_theme_directory(tmp_theme)

    def test_prohibited_extension_rejected(self, tmp_theme: Path) -> None:
        (tmp_theme / "script.qml").write_text("import QtQuick 2.0")
        with pytest.raises(SteamZeroError, match=r"proibido|unsafe"):
            validate_theme_directory(tmp_theme)

    def test_directory_name_mismatch_rejected(self, tmp_theme: Path) -> None:
        renamed = tmp_theme.parent / "wrong-name"
        tmp_theme.rename(renamed)
        with pytest.raises(SteamZeroError, match="difere"):
            validate_theme_directory(renamed)
