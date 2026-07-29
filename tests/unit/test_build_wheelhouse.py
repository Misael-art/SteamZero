# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""HOST-ACTIVATION-01 — o wheelhouse precisa provar de onde veio.

Um diretório de wheels sem procedência não é utilizável: os arquivos parecem
corretos, instalam sem reclamar, e ninguém consegue afirmar de onde vieram. O
repositório tinha um assim — 7,2 MB, não rastreado, origem desconhecida.

A validação devolve LISTA de problemas em vez de levantar na primeira: quem
instala precisa ver tudo que está errado de uma vez, não descobrir um problema
por execução.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from build_wheelhouse import SCHEMA_VERSION, build_manifest, validate

WHEEL = "attrs-26.1.0-py3-none-any.whl"


@pytest.fixture
def wheelhouse(tmp_path: Path) -> Path:
    house = tmp_path / "wheels"
    house.mkdir()
    (house / WHEEL).write_bytes(b"conteudo do wheel")
    (house / "pillow-12.3.0-cp314-cp314-manylinux_2_28_x86_64.whl").write_bytes(b"outro")
    return house


@pytest.fixture
def lock(tmp_path: Path) -> Path:
    path = tmp_path / "requirements-runtime.lock"
    path.write_text("attrs==26.1.0 --hash=sha256:0\n", encoding="utf-8")
    return path


@pytest.fixture
def manifest(wheelhouse: Path, lock: Path) -> dict[str, Any]:
    return build_manifest(wheelhouse=wheelhouse, lock=lock, package_version="0.1.0a38")


class TestTheManifestRecordsProvenance:
    def test_every_required_top_level_field_is_present(self, manifest: dict[str, Any]) -> None:
        for field in (
            "schemaVersion",
            "sourceCommit",
            "packageVersion",
            "requirementsLockSha256",
            "generatedAt",
            "generatorVersion",
            "dependencies",
        ):
            assert field in manifest, field

    def test_every_dependency_carries_hash_size_and_tags(self, manifest: dict[str, Any]) -> None:
        for entry in manifest["dependencies"]:
            for field in (
                "filename",
                "sha256",
                "size",
                "package",
                "version",
                "pythonTag",
                "abiTag",
                "platformTag",
            ):
                assert field in entry, (entry["filename"], field)

    def test_the_hash_is_of_the_real_file(self, manifest: dict[str, Any], wheelhouse: Path) -> None:
        entry = next(item for item in manifest["dependencies"] if item["filename"] == WHEEL)
        assert entry["sha256"] == hashlib.sha256((wheelhouse / WHEEL).read_bytes()).hexdigest()

    def test_the_tags_come_from_the_wheel_name(self, manifest: dict[str, Any]) -> None:
        entry = next(item for item in manifest["dependencies"] if item["filename"] == WHEEL)
        assert entry["package"] == "attrs"
        assert entry["version"] == "26.1.0"
        assert entry["pythonTag"] == "py3"
        assert entry["abiTag"] == "none"
        assert entry["platformTag"] == "any"

    def test_the_run_id_is_recorded_when_ci_provides_it(
        self, wheelhouse: Path, lock: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem ele, dois artefatos do mesmo commit não são distinguíveis."""
        monkeypatch.setenv("GITHUB_RUN_ID", "30409825379")
        monkeypatch.setenv("GITHUB_REPOSITORY", "Misael-art/SteamZero")
        built = build_manifest(wheelhouse=wheelhouse, lock=lock, package_version="0.1.0a38")
        assert built["githubRunId"] == "30409825379"
        assert built["githubRepository"] == "Misael-art/SteamZero"

    def test_the_steamzero_wheel_is_separate_from_the_dependencies(
        self, wheelhouse: Path, lock: Path
    ) -> None:
        wheel = wheelhouse / "steamzero-0.1.0a38-py3-none-any.whl"
        wheel.write_bytes(b"o pacote")
        built = build_manifest(
            wheelhouse=wheelhouse, lock=lock, package_version="0.1.0a38", steamzero_wheel=wheel
        )
        assert built["wheel"]["package"] == "steamzero"
        assert wheel.name not in {item["filename"] for item in built["dependencies"]}

    def test_the_release_id_is_recorded_when_known(self, wheelhouse: Path, lock: Path) -> None:
        built = build_manifest(
            wheelhouse=wheelhouse,
            lock=lock,
            package_version="0.1.0a38",
            release_id="0.1.0a38-51e9e1e35f1f",
        )
        assert built["releaseId"] == "0.1.0a38-51e9e1e35f1f"


class TestValidationRefusesWhatItShould:
    def test_a_clean_set_passes(
        self, manifest: dict[str, Any], wheelhouse: Path, lock: Path
    ) -> None:
        manifest["sourceCommit"] = "51e9e1e35f1f08038e9766ac9dfc1b59f6b851d0"
        manifest["sourceTreeState"] = "clean"
        assert validate(manifest, wheelhouse, lock) == []

    def test_a_tampered_wheel_is_refused(self, manifest: dict[str, Any], wheelhouse: Path) -> None:
        """O caso que o hash existe para pegar."""
        manifest["sourceCommit"] = "51e9e1e3"
        manifest["sourceTreeState"] = "clean"
        (wheelhouse / WHEEL).write_bytes(b"conteudo TROCADO")
        problems = validate(manifest, wheelhouse)
        assert any("sha256" in problem for problem in problems)

    def test_a_missing_wheel_is_refused(self, manifest: dict[str, Any], wheelhouse: Path) -> None:
        manifest["sourceCommit"] = "51e9e1e3"
        manifest["sourceTreeState"] = "clean"
        (wheelhouse / WHEEL).unlink()
        assert any("ausente" in problem for problem in validate(manifest, wheelhouse))

    def test_an_undeclared_wheel_is_refused(
        self, manifest: dict[str, Any], wheelhouse: Path
    ) -> None:
        """É exatamente a forma de um wheel de origem desconhecida entrar.

        Sem esta checagem, alguém copiaria o `wheelhouse/` antigo por cima e o
        conjunto passaria: os declarados conferem, e o intruso viaja junto.
        """
        manifest["sourceCommit"] = "51e9e1e3"
        manifest["sourceTreeState"] = "clean"
        (wheelhouse / "intruso-1.0-py3-none-any.whl").write_bytes(b"de onde veio isso")
        problems = validate(manifest, wheelhouse)
        assert any("não declarado" in problem for problem in problems)

    def test_a_dirty_tree_is_refused(self, manifest: dict[str, Any], wheelhouse: Path) -> None:
        """Artefato de release não sai de árvore suja.

        Verificado de verdade: a primeira geração local reprovou por isto, e
        estava certa.
        """
        manifest["sourceCommit"] = "51e9e1e3"
        manifest["sourceTreeState"] = "dirty"
        assert any("árvore suja" in problem for problem in validate(manifest, wheelhouse))

    def test_an_unknown_commit_is_refused(self, manifest: dict[str, Any], wheelhouse: Path) -> None:
        manifest["sourceCommit"] = "unknown"
        manifest["sourceTreeState"] = "clean"
        assert any("não rastreável" in problem for problem in validate(manifest, wheelhouse))

    def test_a_divergent_lock_is_refused(
        self, manifest: dict[str, Any], wheelhouse: Path, lock: Path
    ) -> None:
        """O lock é parte da autoridade: outro lock, outro conjunto."""
        manifest["sourceCommit"] = "51e9e1e3"
        manifest["sourceTreeState"] = "clean"
        lock.write_text("attrs==99.0.0\n", encoding="utf-8")
        assert any(
            "lock não confere" in problem for problem in validate(manifest, wheelhouse, lock)
        )

    def test_an_incompatible_schema_is_refused(
        self, manifest: dict[str, Any], wheelhouse: Path
    ) -> None:
        manifest["schemaVersion"] = SCHEMA_VERSION + 99
        problems = validate(manifest, wheelhouse)
        assert problems and "schemaVersion" in problems[0]

    @pytest.mark.parametrize(
        "field", ["sourceCommit", "packageVersion", "requirementsLockSha256", "dependencies"]
    )
    def test_a_missing_required_field_is_refused(
        self, manifest: dict[str, Any], wheelhouse: Path, field: str
    ) -> None:
        manifest[field] = None
        assert any(field in problem for problem in validate(manifest, wheelhouse))

    def test_every_problem_is_reported_at_once(
        self, manifest: dict[str, Any], wheelhouse: Path
    ) -> None:
        """Descobrir um problema por execução transforma a validação em tortura."""
        manifest["sourceCommit"] = "51e9e1e3"
        manifest["sourceTreeState"] = "clean"
        (wheelhouse / WHEEL).write_bytes(b"trocado")
        (wheelhouse / "intruso-1.0-py3-none-any.whl").write_bytes(b"intruso")
        assert len(validate(manifest, wheelhouse)) >= 2


class TestTheUnknownWheelhouseIsNeverUsed:
    def test_the_untracked_directory_is_not_referenced_by_the_tooling(self) -> None:
        """O `wheelhouse/` de origem desconhecida não entra nem como fallback.

        Ele continua no disco do desenvolvedor, intocado. O que não pode é
        alguma ferramenta apontar para ele.
        """
        root = Path(__file__).resolve().parents[2]
        source = (root / "tools" / "build_wheelhouse.py").read_text(encoding="utf-8")
        assert '"wheelhouse"' not in source
        assert "/ 'wheelhouse'" not in source

    def test_the_default_output_is_under_dist(self) -> None:
        import build_wheelhouse

        assert "dist" in str(build_wheelhouse.ROOT / "dist" / "runtime-wheelhouse")


class TestTheManifestSerializes:
    def test_it_survives_json_round_trip(self, manifest: dict[str, Any]) -> None:
        restored = json.loads(json.dumps(manifest, ensure_ascii=False))
        assert restored == manifest


class TestTheProductWheelIsNotADependency:
    """O wheel do SteamZero vive fora do wheelhouse.

    A primeira versão o procurava DENTRO e reprovava um conjunto correto — o CI
    pegou isso: "declarado no manifesto e ausente: steamzero-0.1.0a38...". Ele é
    o produto, não dependência; o manifesto o registra por procedência.
    """

    def test_a_wheel_outside_the_wheelhouse_is_checked_where_it_is(
        self, wheelhouse: Path, lock: Path, tmp_path: Path
    ) -> None:
        wheel = tmp_path / "steamzero-0.1.0a38-py3-none-any.whl"
        wheel.write_bytes(b"o produto")
        manifest = build_manifest(
            wheelhouse=wheelhouse, lock=lock, package_version="0.1.0a38", steamzero_wheel=wheel
        )
        manifest["sourceCommit"] = "51e9e1e3"
        manifest["sourceTreeState"] = "clean"
        assert validate(manifest, wheelhouse, lock, wheel) == []

    def test_a_tampered_product_wheel_is_refused(
        self, wheelhouse: Path, lock: Path, tmp_path: Path
    ) -> None:
        wheel = tmp_path / "steamzero-0.1.0a38-py3-none-any.whl"
        wheel.write_bytes(b"o produto")
        manifest = build_manifest(
            wheelhouse=wheelhouse, lock=lock, package_version="0.1.0a38", steamzero_wheel=wheel
        )
        manifest["sourceCommit"] = "51e9e1e3"
        manifest["sourceTreeState"] = "clean"
        wheel.write_bytes(b"o produto TROCADO")
        assert any("sha256" in problem for problem in validate(manifest, wheelhouse, lock, wheel))

    def test_a_missing_product_wheel_is_refused(
        self, wheelhouse: Path, lock: Path, tmp_path: Path
    ) -> None:
        wheel = tmp_path / "steamzero-0.1.0a38-py3-none-any.whl"
        wheel.write_bytes(b"o produto")
        manifest = build_manifest(
            wheelhouse=wheelhouse, lock=lock, package_version="0.1.0a38", steamzero_wheel=wheel
        )
        manifest["sourceCommit"] = "51e9e1e3"
        manifest["sourceTreeState"] = "clean"
        wheel.unlink()
        assert any("ausente" in problem for problem in validate(manifest, wheelhouse, lock, wheel))

    def test_the_product_wheel_inside_the_house_is_not_an_intruder(
        self, wheelhouse: Path, lock: Path
    ) -> None:
        """Se ele estiver dentro, é declarado — não pode virar 'não declarado'."""
        wheel = wheelhouse / "steamzero-0.1.0a38-py3-none-any.whl"
        wheel.write_bytes(b"o produto")
        manifest = build_manifest(
            wheelhouse=wheelhouse, lock=lock, package_version="0.1.0a38", steamzero_wheel=wheel
        )
        manifest["sourceCommit"] = "51e9e1e3"
        manifest["sourceTreeState"] = "clean"
        assert validate(manifest, wheelhouse, lock, wheel) == []
