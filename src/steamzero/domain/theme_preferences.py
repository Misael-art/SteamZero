from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from steamzero.core import paths, transaction
from steamzero.core.errors import SteamZeroError

_PREFERENCE_FILENAME = "theme-preference-v1.json"


class ThemePreferenceManager:
    """Gerencia a preferência de tema ativo com plano/preview/confirmacao/rollback.

    Segue o padrao transactional do SteamZero: plan_activate -> apply -> rollback.
    Cada ativacao de tema cria um plano transacional; a preferencia e persistida
    em theme-preference-v1.json no diretorio XDG config.
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir = config_dir or paths.config_home()
        self._path = self._config_dir / _PREFERENCE_FILENAME

    def _preference_path(self) -> Path:
        return self._path

    def _read_preference(self) -> dict[str, Any] | None:
        path = self._path
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_bytes())
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(raw, dict):
            return None
        return raw

    def _serialize(self, theme_id: str, version: str, previous: dict[str, Any] | None) -> bytes:
        revision = (previous.get("revision", 0) + 1) if previous else 0
        pref = {
            "schemaVersion": 1,
            "themeId": theme_id,
            "themeVersion": version,
            "revision": revision,
        }
        return json.dumps(pref, indent=2, ensure_ascii=False).encode("utf-8")

    def plan_activate(
        self, theme_id: str, version: str, *, previous: dict[str, Any] | None = None
    ) -> transaction.Plan | None:
        """Cria um plano transacional para ativar um tema.

        Se *previous* for fornecido (preferencia atual lida pelo chamador),
        retorna ``None`` quando o tema já está ativo. Essa é uma operação
        informativa: não cria plano, não pede confirmação e não altera a
        preferência persistida.
        """
        if previous and previous.get("themeId") == theme_id:
            return None
        content = self._serialize(theme_id, version, previous)
        target = self._preference_path()
        return transaction.plan_write_files(
            {target: content},
            root=self._config_dir,
            kind="theme.preference.activate",
        )

    def load_plan(self, plan_id: str) -> transaction.Plan:
        plan = transaction.load_plan(plan_id)
        if not plan.kind.startswith("theme.preference."):
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail=f"plano {plan_id} nao pertence a preferencias de tema (kind={plan.kind})",
            )
        return plan

    def apply(self, plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        """Aplica o plano de ativacao de tema."""
        plan = self.load_plan(plan_id)
        self._validate_plan_ownership(plan)

        def verify() -> None:
            path = Path(plan.actions[0].target)
            if not path.is_file():
                raise RuntimeError("preferencia de tema nao foi escrita")
            try:
                raw = json.loads(path.read_bytes())
            except (json.JSONDecodeError, OSError) as exc:
                raise RuntimeError(f"preferencia de tema ilegivel: {exc}") from exc
            if not isinstance(raw.get("themeId"), str):
                raise RuntimeError("preferencia de tema sem themeId valido")

        return transaction.apply(plan_id, confirm_token, smoke=verify)

    def rollback(self, operation_id: str) -> transaction.RollbackResult:
        if not operation_id or not operation_id.strip():
            raise SteamZeroError("E-API-SCHEMA", detail="operation_id vazio")
        return transaction.rollback(operation_id, reason="theme-preference")

    def _validate_plan_ownership(self, plan: transaction.Plan) -> None:
        actual_root = str(Path(plan.root).resolve())
        expected_root = str(self._config_dir.resolve())
        if actual_root != expected_root:
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail=f"plano tem root {actual_root} mas o manager espera {expected_root}",
            )
