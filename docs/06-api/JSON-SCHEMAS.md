# JSON-SCHEMAS — índice e exemplos de schemas

Schemas JSON (draft 2020-12) versionados em `schemas/` no repositório (Fase 1); este documento é o índice normativo e traz exemplos-chave.

| Schema | Cobre | Referência |
|---|---|---|
| `envelope-v2.schema.json` | Saída CLI/API | CLI-CONTRACT |
| `plan-v1.schema.json` | Plano transacional | MANIFEST-SCHEMAS §4 |
| `desktop-plan-v1.schema.json` | Plano G-STATE do Desktop Experience | MANIFEST-SCHEMAS §7 |
| `desktop-conflict-plan-v1.schema.json` | Plano confirmado para liberar owner externo | MANIFEST-SCHEMAS §7 |
| `desktop-status-v1.schema.json` | Contexto/status Desktop | MANIFEST-SCHEMAS §7 |
| `session-environment-v1.schema.json` | Ambiente Linux read-only da sessão | STEAM-SESSION-ROADMAP R1 |
| `adapter-v1.schema.json` | adapter.json | ADAPTER-MODEL |
| `platform-manifest-v1.schema.json` | registry de plataformas e capacidades | PLATFORM-MANIFEST-V1 |
| `retro-input-profile-v1.schema.json` | perfil semântico versionado de controles | RETRO-INPUT-PROFILE-V1 |
| `feat-playtime-v1.schema.json` | playtime, recentes e continuar jogando | FEAT-PLAYTIME-V1 |
| `screen-cast-v1.schema.json` | estado de sessão de compartilhamento de tela | ADR-0022 / WI-S0 |
| `component-lock-v1.schema.json` | lockfile empacotado de componentes | MANIFEST-SCHEMAS §2 |
| `component-plan-v1.schema.json` | plano Flatpak pinado | MANIFEST-SCHEMAS §4 |
| `backup-manifest-v1.schema.json` | manifesto de backup | BACKUP-FORMAT |
| `bios-db-v1.schema.json` | banco de hashes | MANIFEST-SCHEMAS §5 |
| `profile-v1.schema.json` | presets/perfis | MANIFEST-SCHEMAS §6 |
| `event-v1.schema.json` | eventos/progresso | EVENTS-AND-PROGRESS |
| `error-v1.schema.json` | objeto de erro | ERROR-CATALOG |
| `job-v1.schema.json` | job serializado | JOB-LIFECYCLE |
| `state-export-v1.schema.json` | export do State Store | STATE-MODEL |
| `config-platform-v1.schema.json` | config.toml (via taplo/JSON Schema) | CONFIGURATION-SCHEMAS |
| `support-bundle-v1.schema.json` | índice do bundle | SUPPORT-BUNDLE |
| `emulation-workspace-v1.schema.json` | catálogo de emulação publicado ao shell; `$defs/readiness` é o contrato de prontidão compartilhado | §Prontidão v2 abaixo |

## Contrato de prontidão (`$defs/readiness`) — v2

Fonte de verdade do código: `src/steamzero/domain/readiness.py` (produtores) e
`src/steamzero/ui/qml/readiness.js` (leituras de superfície). Uma única forma de
responder "isto está pronto?" para qualquer painel; nenhum número de prontidão
é derivável de categoria.

Onze campos obrigatórios: `contractVersion`, `state`, `label`, `cause`,
`nextAction`, `blockers`, `verification`, `basis`, `pendingRequired`,
`pendingOptional`, `measure`.

| Campo | Vocabulário | O que responde |
|---|---|---|
| `state` | `ready` `attention` `blocked` `unverified` `unavailable` `planned` `degraded` | que o usuário entende |
| `label` / `cause` / `nextAction` / `blockers` | texto | título, por quê, o que fazer em seguida |
| `verification` | `verified` `not_performed` `not_applicable` `unknown` | se algo foi de fato verificado |
| `basis` | `preflight` `demonstrated_gameplay` `inventory_existence` `existence_only` `none` | com que evidência — preflight ≠ gameplay jogado |
| `pendingRequired` / `pendingOptional` | inteiro ou `null` | o que falta, separado por obrigatoriedade |
| `measure` | objeto de 7 campos | a proporção mensurada, quando existe |

`measure` = `dimension`, `dimensionLabel`, `numerator`, `denominator`, `percent`,
`absentReason`, `counts`. `dimension` ∈ `required_requirements`
`optional_requirements` `game_inventory` `launch_preflight` `not_measured`.

Invariantes (rejeitados na construção, não apenas no layout):

1. **Denominador zero não é percentual.** `proportion()` levanta
   `ValueError` se `denominator == 0` sem `absentReason`, e nunca produz 100 nem
   0 nesse caso — `percent` fica ausente com `absentReason` registrado. O
   produtor que antes publicava `100%` num conjunto vazio agora publica a razão
   da ausência.
2. **`percent` é nullable e nunca se inventa.** Sem numerador/denominador é
   obrigatório declarar `absentReason` ∈ `zero_denominator` `not_measured`
   `missing_data` `legacy_contract`. `absentReason` só acompanha percent ausente.
3. **Numerator não excede denominator**, e contagem negativa é recusada.
4. **Dimensão nomeada.** Um percentual sem `dimension` não é publicado; a
   superfície exibe a legenda da dimensão junto ao número, porque "67%" sem
   "de quê" é o defeito que este contrato fecha.
5. **Obrigatoriedade é critério único.** `requirement_in_force()` é o julgamento
   compartilhado (`ok` satisfaz; `missing`/`outdated`/`incomplete` pendem;
   `not-required` está fora de vigor). Produtor que reimplementar a regra volta
   a produzir números divergentes entre si.
6. **"Pronto" exige evidência de verificação.** `state="ready"` é recusado com
   `pendingRequired > 0`, com `verification ≠ verified` e com `basis` fora de
   `preflight`/`demonstrated_gameplay` (`READY_BASES`). `inventory_existence` e
   `existence_only` continuam válidas para outros estados — existir jogo
   inventariado ou existir um abridor é informação honesta sobre o que *há*, mas
   não é evidência de que algo está pronto, e foi exatamente essa leitura que
   produziu o `100%` da Emulação.

Compatibilidade: `readiness` aceita `oneOf` entre v1 (`percent` obrigatório, com
`title`/`detail`/`blockers` opcionais) e v2 (os onze campos acima). v1 existe só
para não invalidar cache e fixtures anteriores; nenhum produtor emite v1. `normalize_readiness()` converte payload legado para
`state="unverified"` com `absentReason="legacy_contract"` — **o número some da
tela**, porque uma proporção cuja dimensão nunca existiu não pode ser relida
como proporção de outra coisa.

Consumo no QML (`readiness.js`, `.pragma library`): a cor vem de `state`
(`tone()`: `ready`→verde, `blocked`→vermelho, `attention`/`degraded`/
`unavailable`→âmbar, resto→neutro), nunca do percentual; o número vem de
`percentText(readiness, "—")`; a barra de progresso só aparece com medição real
(`showsProgress`). Página nenhuma reimplementa estas regras — o harness
`tests/qml/check_readiness_surface.qml` trava a delegação por mutação.

## Exemplo: `event-v1.schema.json` (núcleo)

```json
{ "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["seq","ts","kind","correlationId"],
  "properties": {
    "seq": {"type":"integer","minimum":0},
    "ts": {"type":"string","format":"date-time"},
    "kind": {"enum":["job.progress","job.state","session.state","session.environment","entity.changed","alert"]},
    "jobId": {"type":"string"}, "correlationId": {"type":"string"},
    "progress": {"type":"object","properties":{
      "stage":{"type":"string"}, "current":{"type":"number"},
      "total":{"type":["number","null"]}, "unit":{"enum":["bytes","items","steps"]},
      "rate":{"type":["number","null"]}, "currentItem":{"type":["string","null"]}}},
    "state": {"type":"string"}, "error": {"$ref":"error-v1.schema.json"}
  }, "additionalProperties": false }
```

## Regras

1. `additionalProperties:false` em todo schema de **entrada** (rejeitar campos desconhecidos); saídas permitem evolução aditiva com `additionalProperties:true` + campos documentados.
2. IDs: ULID (`^[0-9A-HJKMNP-TV-Z]{26}$`); slugs: `^[a-z0-9][a-z0-9-]{0,62}$` (mesma regex do `pz_boot_valid_id`, common.sh:346).
3. Todo schema tem suíte de exemplos válidos/inválidos versionada (golden tests).
