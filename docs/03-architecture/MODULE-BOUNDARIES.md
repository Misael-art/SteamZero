# MODULE-BOUNDARIES — limites e dependências permitidas

## Grafo de dependências (só é permitido depender "para baixo")

```
ui.gamemode │ ui.desktop │ ui.qam │ cli
        └───────────┬───────────┘
                 api.server (allowlist, schemas, authz, eventos)
                     │
      ┌──────────────┼───────────────┐
   jobs.manager   domain.*        diagnostics
      │              │                │
      └───────► core.transaction ◄────┘
                     │
      ┌──────┬───────┼────────┬──────────┐
  core.state core.fs core.log core.lock core.crypto
      │
  adapters.* (plugáveis; dependem de core.*, nunca de domain.* nem api.*)
      │
  privileged.client ──(IPC)──► steamzero-admin (repo/binário separado)
```

## Contratos entre módulos

| Fronteira | Regra |
|---|---|
| ui.* / cli → api.server | Só ações nomeadas da allowlist com parâmetros schemados; nunca paths absolutos crus vindos da UI (a UI referencia IDs de entidades do State Store) |
| api.server → jobs/domain | Traduz ação→job ou ação→query; não contém regra de domínio |
| domain.* → adapters | Só via interface de capacidade declarada (ADAPTER-MODEL); domain não conhece implementações |
| qualquer → core.fs | Única porta de escrita em disco (staging, atomic write, quarantine); escrita direta é violação de arquitetura detectável por lint/CI |
| qualquer → privileged | Só `privileged.client` com ações da allowlist; nenhuma string de shell atravessa a fronteira |
| adapters → rede | Só via `core.net` (que aplica: manifesto com hash pinado, retry, rate limit, fila offline) |

## Proibições verificáveis em CI

- `eval`, `exec` de string, `shell=True` com f-string: proibidos (lint).
- Import de `adapters.*` dentro de `domain.*`: proibido (import-linter).
- `open(..., "w")`/`os.rename` fora de `core.fs`: proibido (lint custom).
- Chamada de `subprocess` fora de `core.proc`/adapters: proibida.
- Segredos: tipos `Secret[str]` com repr mascarado; log handler rejeita valores não mascarados desse tipo.

## Racional das fronteiras (lições dos fontes)

- EmuDeck mistura UI (zenity) dentro de scripts de instalação (`emuDeckDuckStation.sh:25` chama zenity no meio da migração) → aqui, UI e mutação nunca coabitam.
- RetroDECK acopla Configurator a funções internas via nomes de função em JSON (`component_manifest.json` → `"zenity": "configurator_*_dialog"`) — o conceito declarativo fica, mas o alvo passa a ser **ação registrada com schema**, não nome de função arbitrário.
- PhaseZero separa UI↔orchestrator por contrato JSON (padrão a preservar) mas o orchestrator é monólito → aqui, módulos com fronteiras de import verificadas.
