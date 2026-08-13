# ACTIVE-WORK — SteamZero

<!-- Gerado por tools/project_status.py; nao editar manualmente. -->

Somente workstreams `active` aparecem aqui. O coordenador deve criar ou atualizar o registro antes de delegar trabalho.

| Workstream | Item | Branch | Base | Owner | Escopo exclusivo | Proxima acao |
|---|---|---|---|---|---|---|
| WS-2026-08-G45-AUTOCONFIG | SZ-EMULATION-M10 | `codex/g45-autoconfig-gerenciado` | `e71d9b4` | g45-autoconfig | src/steamzero/domain/retroarch_autoconfig.py<br>src/steamzero/adapters/input_devices.py<br>tests/unit/test_retroarch_autoconfig.py<br>tests/unit/test_input_devices.py | Resolver o indice fisico contra o autoconfig real do dispositivo e gravar arquivo gerenciado com marcador, sem tocar no retroarch.cfg. |
| WS-2026-08-HARMONIZE-A45 | SZ-GOVERNANCE-STATUS | `codex/harmonize-main-a45` | `245e8d8e9dd3977f15f9402143d6e432966e7202` | harmonize-a45-agent | docs/status<br>tools/project_status.py<br>src/steamzero/diagnostics/doctor.py<br>src/steamzero/adapters/release_convergence.py<br>tests/unit/test_project_status.py<br>tests/unit/test_doctor.py<br>tests/unit/test_theme_editor.py<br>src/steamzero/domain/theme_editor.py<br>src/steamzero/adapters/steam_shortcuts.py<br>src/steamzero/adapters/steam_rom_manager.py<br>src/steamzero/adapters/es_de.py<br>docs/adr | UI audit preservada via cherry-pick; corrigir status-check WORKLOG append-only e doctor falso verde; depois ADRs/M11/G37. |
| WS-2026-08-M10 | SZ-EMULATION-M10 | `codex/fase1-cores-laco-primario` | `e1e2c73` | m10-vm | tools/vm_harness<br>tests/integration/test_vm_harness.py | Provar um ciclo minimo de RetroArch antes de ampliar a matriz. |
| WS-2026-08-M11 | SZ-FRONTEND-RETROFE | `codex/m11-frontends-idempotentes` | `e1e2c73` | m11-frontends | src/steamzero/adapters/frontends<br>tests/integration/test_frontend_adapters.py | Finalizar idempotencia e preparar integracao isolada do adapter M11. |
