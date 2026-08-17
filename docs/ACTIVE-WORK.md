# ACTIVE-WORK — SteamZero

<!-- Gerado por tools/project_status.py; nao editar manualmente. -->

Somente workstreams `active` aparecem aqui. O coordenador deve criar ou atualizar o registro antes de delegar trabalho.

| Workstream | Item | Branch | Base | Owner | Escopo exclusivo | Proxima acao |
|---|---|---|---|---|---|---|
| WS-2026-08-HARMONIZE-A45 | SZ-GOVERNANCE-STATUS | `codex/harmonize-main-a45` | `245e8d8e9dd3977f15f9402143d6e432966e7202` | harmonize-a45-agent | docs/status<br>tools/project_status.py<br>src/steamzero/diagnostics/doctor.py<br>src/steamzero/adapters/release_convergence.py<br>tests/unit/test_project_status.py<br>tests/unit/test_doctor.py<br>tests/unit/test_theme_editor.py<br>src/steamzero/domain/theme_editor.py<br>src/steamzero/adapters/steam_shortcuts.py<br>src/steamzero/adapters/steam_rom_manager.py<br>src/steamzero/adapters/es_de.py<br>docs/adr | UI audit preservada via cherry-pick; corrigir status-check WORKLOG append-only e doctor falso verde; depois ADRs/M11/G37. |
| WS-2026-08-M10 | SZ-EMULATION-M10 | `codex/fase1-cores-laco-primario` | `e1e2c73` | m10-vm | tools/vm_harness<br>tests/integration/test_vm_harness.py | Provar um ciclo minimo de RetroArch antes de ampliar a matriz. |
| WS-2026-08-M11 | SZ-FRONTEND-RETROFE | `codex/m11-frontends-idempotentes` | `e1e2c73` | m11-frontends | src/steamzero/adapters/frontends<br>tests/integration/test_frontend_adapters.py | Finalizar idempotencia e preparar integracao isolada do adapter M11. |
| WS-2026-08-THEME-ASSET-RECIPES | SZ-THEME-ENGINE | `codex/theme-engine-asset-recipes` | `e71d9b41982de74328cd9956b447f6009cbee509` | codex-theme-engine | src/steamzero/domain/asset_recipes.py<br>src/steamzero/schemas/asset-recipe-v1.schema.json<br>src/steamzero/themes/org.steamzero.asset-recipes-demo<br>src/steamzero/ui/qml/AssetRecipePreview.qml<br>tests/unit/test_asset_recipes.py<br>tests/qml/check_asset_recipe_preview.qml | Fechar o primeiro slice verificavel: um asset-fonte transparente gera variantes declarativas em runtime, com cache descartavel, fallback seguro, preview real e evidencia fisica. |
