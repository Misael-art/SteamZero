# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Importacao de um pacote de tema do PROPRIO SteamZero pela central.

Fecha o ciclo exportar -> compartilhar -> importar. Criar, editar, salvar e
exportar ja existiam; importar so existia por linha de comando (`theme
install`), o que nao serve a quem esta na central.

Distinto de `test_theme_import_esde.py`: la o formato e de terceiro e a
conversao nao e fiel; aqui o manifesto ja esta no formato certo e o que importa
sao as garantias de origem — arquivo local, manifesto da raiz, teto de leitura e
sobrescrita explicita.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError


class TestImportingASteamZeroPackage:
    """Fecha o ciclo que o operador pediu: exportar, compartilhar, importar.

    Criar, editar, salvar e exportar ja existiam. Importar so existia por linha
    de comando (`theme install`), o que nao serve a quem esta na central.
    """

    @staticmethod
    def _dashboard(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
        from steamzero.adapters.desktop_dashboard import DesktopDashboard

        return DesktopDashboard()

    @staticmethod
    def _exported(dashboard, tmp_path: Path, name: str = "Meu Tema") -> tuple[Path, str]:  # type: ignore[no-untyped-def]
        session = dashboard.editor_create(name, extends="org.steamzero.aura")
        dashboard.editor_set_tokens(str(session["sessionId"]), "color", {"accent": "#ff7700"})
        saved = dashboard.editor_save(str(session["sessionId"]))
        reopened = dashboard.editor_load(str(saved["themeId"]))
        package = tmp_path / "tema.zip"
        package.write_bytes(dashboard.editor_export_zip(str(reopened["sessionId"])))
        return package, str(saved["themeId"])

    def test_a_theme_survives_the_export_import_round_trip(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        dashboard = self._dashboard(tmp_path, monkeypatch)
        try:
            package, theme_id = self._exported(dashboard, tmp_path)
            result = dashboard.theme_import_zip_apply(str(package), overwrite=True)
            assert result["themeId"] == theme_id
            assert theme_id in {item["id"] for item in dashboard.theme_list()}
        finally:
            dashboard.close_request_context()

    def test_inspect_warns_before_overwriting_an_installed_theme(
        self, tmp_path, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        """`alreadyInstalled` e a diferenca entre uma escolha e uma perda."""
        dashboard = self._dashboard(tmp_path, monkeypatch)
        try:
            package, theme_id = self._exported(dashboard, tmp_path)
            report = dashboard.theme_import_zip_inspect(str(package))
            assert report["themeId"] == theme_id
            assert report["alreadyInstalled"] is True
            assert report["extends"] == "org.steamzero.aura"
        finally:
            dashboard.close_request_context()

    def test_importing_over_an_installed_theme_needs_overwrite(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Sobrescrever nao pode acontecer por omissao de campo."""
        dashboard = self._dashboard(tmp_path, monkeypatch)
        try:
            package, _theme_id = self._exported(dashboard, tmp_path)
            with pytest.raises(SteamZeroError, match="já instalado"):
                dashboard.theme_import_zip_apply(str(package))
        finally:
            dashboard.close_request_context()

    def test_inspect_writes_nothing(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Quem so quer ver o que ha no pacote nao instalou nada ainda."""
        dashboard = self._dashboard(tmp_path, monkeypatch)
        try:
            package, _theme_id = self._exported(dashboard, tmp_path)
            before = {item["id"] for item in dashboard.theme_list()}
            digest = package.read_bytes()

            dashboard.theme_import_zip_inspect(str(package))

            assert {item["id"] for item in dashboard.theme_list()} == before
            assert package.read_bytes() == digest
        finally:
            dashboard.close_request_context()

    def test_a_url_is_refused_by_the_central_import(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Baixar de endereco digitado na interface e outra funcionalidade.

        Ela exige consentimento, verificacao de tamanho e de origem — e o
        marketplace ja a cobre atras de opt-in. Aceitar URL aqui abriria um
        segundo caminho de download sem nenhuma dessas garantias.
        """
        dashboard = self._dashboard(tmp_path, monkeypatch)
        try:
            with pytest.raises(SteamZeroError, match="arquivo local"):
                dashboard.theme_import_zip_inspect("https://exemplo.invalido/tema.zip")
        finally:
            dashboard.close_request_context()

    def test_a_package_without_manifest_fails_closed(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        import zipfile

        dashboard = self._dashboard(tmp_path, monkeypatch)
        try:
            package = tmp_path / "vazio.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("leiame.txt", "sem manifesto")
            with pytest.raises(SteamZeroError, match=r"theme\.json"):
                dashboard.theme_import_zip_inspect(str(package))
        finally:
            dashboard.close_request_context()

    def test_the_root_manifest_wins_over_a_nested_one(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Um tema aninhado nao pode se passar por outro."""
        import json as _json
        import zipfile

        dashboard = self._dashboard(tmp_path, monkeypatch)
        try:
            package = tmp_path / "aninhado.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr(
                    "fundo/fundo/theme.json",
                    _json.dumps({"id": "org.impostor", "name": "Impostor", "version": "9.9.9"}),
                )
                archive.writestr(
                    "theme.json",
                    _json.dumps({"id": "org.verdadeiro", "name": "Verdadeiro", "version": "1.0.0"}),
                )
            assert dashboard.theme_import_zip_inspect(str(package))["themeId"] == "org.verdadeiro"
        finally:
            dashboard.close_request_context()

    def test_an_oversized_manifest_is_refused(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Manifesto inflado nao pode virar memoria antes de qualquer validacao.

        O teto existia sem teste: a mutacao que o desliga passava. Descoberto
        por mutacao, nao por leitura.
        """
        import json as _json
        import zipfile

        from steamzero.adapters import desktop_dashboard

        dashboard = self._dashboard(tmp_path, monkeypatch)
        try:
            package = tmp_path / "inflado.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr(
                    "theme.json",
                    _json.dumps({"id": "org.grande", "name": "G" * 4096, "version": "1.0.0"}),
                )
            monkeypatch.setattr(desktop_dashboard, "_THEME_MANIFEST_MAX_BYTES", 64)
            with pytest.raises(SteamZeroError, match="teto"):
                dashboard.theme_import_zip_inspect(str(package))
        finally:
            dashboard.close_request_context()
