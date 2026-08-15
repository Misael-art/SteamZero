# ACTIVE-WORK — SteamZero

<!-- Gerado por tools/project_status.py; nao editar manualmente. -->

Somente workstreams `active` aparecem aqui. O coordenador deve criar ou atualizar o registro antes de delegar trabalho.

| Workstream | Item | Branch | Base | Owner | Escopo exclusivo | Proxima acao |
|---|---|---|---|---|---|---|
| WS-2026-08-HARMONIZE-A45 | SZ-GOVERNANCE-STATUS | `codex/harmonize-main-a45` | `245e8d8e9dd3977f15f9402143d6e432966e7202` | harmonize-a45-agent | docs/status<br>tools/project_status.py<br>src/steamzero/diagnostics/doctor.py<br>src/steamzero/adapters/release_convergence.py<br>tests/unit/test_project_status.py<br>tests/unit/test_doctor.py<br>tests/unit/test_theme_editor.py<br>src/steamzero/domain/theme_editor.py<br>src/steamzero/adapters/steam_shortcuts.py<br>src/steamzero/adapters/steam_rom_manager.py<br>src/steamzero/adapters/es_de.py<br>docs/adr | UI audit preservada via cherry-pick; corrigir status-check WORKLOG append-only e doctor falso verde; depois ADRs/M11/G37. |
| WS-2026-08-HOST-RELEASE-UPDATE | SZ-HOST-RELEASE-UPDATE | `codex/transactional-host-update` | `e71d9b41982de74328cd9956b447f6009cbee509` | codex-host-update | tools/release_host.py<br>tests/unit/test_release_host.py<br>docs/09-operations/RELEASE-HOST-AUTOMATION.md<br>docs/09-operations/UPDATE-AND-ROLLBACK.md | Implementar update transacional sem tocar no host real e provar recuperacao por testes com injeção de falha. |
| WS-2026-08-M10 | SZ-EMULATION-M10 | `codex/fase1-cores-laco-primario` | `e1e2c73` | m10-vm | tools/vm_harness<br>tests/integration/test_vm_harness.py | Provar um ciclo minimo de RetroArch antes de ampliar a matriz. |
| WS-2026-08-M11 | SZ-FRONTEND-RETROFE | `codex/m11-frontends-idempotentes` | `e1e2c73` | m11-frontends | src/steamzero/adapters/frontends<br>tests/integration/test_frontend_adapters.py | Finalizar idempotencia e preparar integracao isolada do adapter M11. |
