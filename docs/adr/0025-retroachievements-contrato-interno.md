# ADR-0025 — RetroAchievements: contrato interno de achievements, autenticação indireta e modo hardcore

**Status:** aceito

## Contexto

O item `SZ-RETROACHIEVEMENTS` planeja integração com o ecossistema RetroAchievements
sem copiar o payload proprietário de APIs externas para dentro do produto. A lição
das frentes anteriores é a mesma: contrato interno estável, porta independente do
fornecedor, credencial no keyring e verdade honesta para a UI. Este ADR define o
contrato interno de eventos de achievement e os limites de responsabilidade entre
adapter, domínio, keyring e UI. Nada aqui implementa runtime nem documenta endpoints
externos como fatos sem fonte oficial.

## Objetivo e não objetivos

**Objetivos**

- Definir identidade de conta por referência opaca + `credentialRef` no keyring;
- definir identificação de jogo por hash local versionado (nunca a ROM);
- definir estados de achievement, fila offline idempotente e modo hardcore;
- garantir que a UI futura nunca confunda offline com sincronizado, nem apague
  conquistas locais por falha remota.

**Não objetivos**

- Documentar endpoints, formatos ou semântica proprietária da API externa;
- implementar adapter, chaves do keyring, fila, rede ou CLI;
- enviar ROM, hash parcial ou conteúdo do jogo a qualquer serviço;
- leaderboards, sessões de jogo remotas ou modo hardcore validado por terceiros.

## Vocabulário

| Termo | Significado |
|---|---|
| conta | identidade do usuário no ecossistema, referida por `reference` opaco. |
| credentialRef | caminho do segredo no keyring; único meio de autenticação. |
| reconhecimento | resultado da identificação do jogo (`recognized`/`unrecognized`/`ambiguous`/`incompatible-*`). |
| outbox | fila local limitada de desbloqueios pendentes de sincronização. |
| idempotencyKey | chave que torna reenvios de um evento inofensivos. |
| hardcore | modo que proíbe save state, rewind, cheats, speed mod e alteração de core/config. |
| degradação | transição observável de hardcore para modo normal, com motivo. |

## Atores e limites de confiança

| Ator | Confia em | Não confia em |
|---|---|---|
| usuário | seus dados locais | serviço remoto para *verdade* local |
| domínio | contracto interno e fila local | payload externo sem normalização |
| adapter | contrato interno | mudanças não versionadas do fornecedor |
| keyring | porta de segredos do produto | nenhum consumidor de payload com token |
| serviço externo | credencial apresentada | nada além do que o contrato externo exige |

O token da conta só existe no keyring; o contrato persistido nunca o contém.

## Identidade

- `account.reference`: `ra-acct-<12 hex>` — opaco, sem nome de usuário ou e-mail.
- `account.authState`: `configured` | `notConfigured` | `invalid` | `expired` |
  `unavailable`.
- `account.credentialRef`: `keyring:steamzero/retroachievements/<nome>` — obrigatório
  quando `configured`; proibido em qualquer outro lugar do envelope.
- `configured` sem `credentialRef` é inválido; `invalid`/`expired` exigem `error`.
- Token nunca entra no envelope persistido (fixture `01-token-embedded`).

## Identificação do jogo

- `game.romHash`: `algorithm` fechado em `sha256` + `digest` de 64 hex, calculado
  localmente e versionado (`ALGORITHM_UNKNOWN` para qualquer outro).
- `game.recognition`: `recognized` | `unrecognized` | `ambiguous` |
  `incompatible-version` | `incompatible-region`.
- `titleId` só existe quando `recognized`.
- **Nenhuma ROM é enviada.** Caminho local é proibido no payload
  (fixture `13-rom-path-in-payload`).
- Estados `unlocked-*` exigem `recognized` (fixture `07-conflicting-duplicate-unlock`).

## Estados de achievement

`state` é enum fechado:

| Estado | Significado | Pode sincronizar? |
|---|---|---|
| `locked` | conquista ainda não desbloqueada | não |
| `unlocked-local` | desbloqueada localmente, sem fila | ainda não |
| `pending-sync` | desbloqueada, aguardando envio (outbox) | sim |
| `unlocked-synced` | confirmada pelo serviço | já sincronizado |
| `rejected` | rejeitada pelo serviço; exige `error` | não |
| `revoked` | revogada pelo serviço | não |
| `unknown` | estado remoto desconhecido; exige prudência | não |

Regras: `pending-sync` exige `outbox`; `outbox` só em `unlocked-local`/`pending-sync`;
`error` só em `rejected`/`revoked`/`unknown`; `rejected` exige `error`.

## Offline

- **Outbox limitada**: `outbox.retryCount` (0..10) e `maxRetries` fixo em 10;
  esgotada, exige `error` (`09-quota-exceeded`).
- **Idempotency key**: `idempotencyKey` obrigatória quando há `outbox`; reenvio do
  mesmo evento é inofensivo (fixtures `06`/`07`/`08` reutilizam a mesma chave).
- **Retomada**: após queda, a fila retoma pelo `eventId`; duplicação é absorvida.
- **Relógio divergente**: eventos carregam `occurredAt` UTC do momento local; o
  serviço é fonte de tempo de confirmação, não de desbloqueio.
- **Conflito**: rejeição remota vira `rejected` com `error.REMOTE_REJECTED`; dados
  conflitantes não são aplicados sobre a verdade local.
- **Expiração**: eventos não confirmados após a janela do produto são
  `unknown`/`rejected` com causa; nunca `unlocked-synced`.

## Hardcore

- `hardcore.active` indica o modo vigente.
- Capacidades proibidas (enum fechado): `save-state`, `rewind`, `cheat`,
  `speed-mod`, `core-change`, `config-change`.
- `active: true` com qualquer capacidade proibida é contradição
  (`11-hardcore-with-save-state`).
- **Transição segura para modo normal**: `degradation` com `reason`
  (`user-requested`, `save-state-requested`, `rewind-requested`, `cheat-detected`,
  `speed-mod-detected`, `core-changed`, `config-changed`) e `at` UTC. `degradation`
  exige `hardcore.active: false`.
- **Motivo observável da recusa**: quem recusa hardcore (UI, core ou adapter) grava
  a causa no `degradation.reason` — nunca falha silenciosa.

## Privacidade e segurança

- Token somente no keyring; `credentialRef` é o único vestígio no envelope.
- Redaction antes de qualquer serialização persistida; senha/token em payload são
  inválidos por schema (`01`/`02`).
- Rate limit: a outbox limita reenvios (`maxRetries`); o adapter deve respeitar
  limites externos sem documentar valores não confirmados.
- Indisponibilidade vira `unavailable`/`API_UNAVAILABLE` com `retryable`; nunca
  apaga dados locais.
- Revogação (`revoked`) e exclusão local são destrutivas só com consentimento
  explícito; retenção mínima de eventos após confirmação.

## Verdade da UI futura

1. Offline não equivale a sincronizado: `unlocked-local`/`pending-sync` nunca
   aparecem como "conquistado online".
2. Dado parcial não equivale a ausência: sem resposta remota, o estado é
   `unknown`, não "nenhum dado".
3. Falha de autenticação não apaga achievements locais: `expired`/`invalid`
   afetam sincronização, não a verdade local.
4. Estado remoto desconhecido permanece `unknown` até confirmação; `rejected` só
   com `error` que explique o motivo.

## Versionamento do contrato

`schemaVersion` fixo em `1`; envelope fechado (`additionalProperties: false`);
campos futuros exigem `v2` negociado (`12-future-unknown-fields`). O contrato interno
não herda versão do fornecedor: mudanças externas são absorvidas pelo adapter e só
chegam ao domínio como novo contrato interno.

## Identificadores e idempotência

- `eventId`/`idempotencyKey`: `raev-<16 hex>`; reenvio usa a mesma chave.
- `outbox.entryId`: `ra-ob-<12 hex>`.
- `achievement.id`: `ra-ach-<1..6 dígitos>`; `titleId`: `ra-game-<1..6 dígitos>`.
- Timestamps UTC (`occurredAt`, `queuedAt`, `degradation.at`), RFC 3339 com `Z`.

## Códigos de erro estáveis

`error.code` enum fechado: `AUTH_EXPIRED`, `AUTH_INVALID`, `QUOTA_EXCEEDED`,
`API_UNAVAILABLE`, `REMOTE_REJECTED`, `HASH_UNKNOWN`, `ALGORITHM_UNKNOWN`,
`TIMESTAMP_INVALID`, `IMPOSSIBLE_TRANSITION`, `CONFLICTING_DUPLICATE`,
`HARDCORE_FORBIDDEN`, `FUTURE_PROTOCOL_FIELDS`, `SENSITIVE_PAYLOAD_REJECTED`.

## Cancelamento e teardown

Cancelar sincronização drena a outbox em estado conhecido (`unknown` ou `rejected`
com causa); nunca descarta desbloqueios locais. Exclusão da conta remove
`credentialRef` e marca estado `notConfigured` após confirmação.

## Comportamento offline

O jogo local funciona sem o serviço; conquistas continuam sendo desbloqueadas
localmente e enfileiradas. Sem serviço, `authState` observável é `unavailable` e a
outbox retém. Sincronização é melhor esforço, nunca bloqueante.

## Rate limit e defesa contra abuso

Outbox com `maxRetries` fixo e `retryCount` limitado; reenvio idempotente; rejeição
duplicada com dados conflitantes é `CONFLICTING_DUPLICATE`; sem tokens em logs.

## Recuperação após queda

Queda do processo: outbox persiste (estado do produto), retomada reenvia com a mesma
`idempotencyKey`. Queda do serviço: `API_UNAVAILABLE` com `retryable`, fila preservada.

## Observabilidade

Permitido: `eventId`, `state`, `error.code`, `retryCount`, `recognition`. Proibido:
token, senha, digests fora do fluxo de identificação, caminho da ROM, identidade
real da conta em logs persistidos.

## Critérios para promover de `planned` para `verified-dev`

- Envelope e fixtures validados por teste contratual (evidência de design).
- Porta interna capaz de produzir/consumir o envelope v1 com keyring fake.
- Ciclo offline → sync verificado em isolamento: desbloqueio local, fila, reenvio
  idempotente, confirmação.
- Degradação hardcore→normal com motivo observável em teste isolado.
- Nenhuma verificação com serviço real acontece sem rede real autorizada.

## Responsabilidades

**Adapter**

- Conversão entre o contrato externo (não documentado aqui) e o envelope v1;
- guardar/renovar credencial via porta do keyring, nunca em memória de payload;
- aplicar rate limit externo; mapear rejeição externa em `error.code` interno;
- nunca emitir `unlocked-synced` sem confirmação recebida.

**Domínio**

- Manter estados, outbox e idempotência; aplicar regras do envelope;
- decidir `recognized`/`unrecognized` a partir do hash local;
- garantir que falha remota nunca altere verdade local;
- orquestrar hardcore e `degradation`.

**Keyring**

- Guardar o token da conta, criá-lo/atualizá-lo/removê-lo sob consentimento;
- expor apenas `credentialRef` ao restante do produto;
- nunca expor o segredo ao domínio, à UI ou a logs.

**UI**

- Exibir estados honestos (ver "Verdade da UI futura");
- solicitar credencial e consentimento; mostrar motivo de `degradation`;
- nunca solicitar token ao usuário para colar no payload.

**Só pode ser validado com serviço real**

- Confirmação real de `unlocked-synced` e `revoked` por terceiro;
- semântica exata de `rejected`/`ambiguous` do fornecedor;
- limites de rate limit e retenção do lado externo.

## Decisões adiadas e perguntas em aberto

- Formato exato de `credentialRef` por backend de keyring (porta existente, sem
  implementação).
- Semântica de leaderboards e outras superfícies externas (fora do v1).
- Política de janela de expiração da outbox (prazo exato a definir com o estado do
  produto).
- Pesquisa oficial necessária: regras de hardcore do ecossistema (não documentar
  sem fonte oficial).

## Consequências

- Positivas: contrato interno estável e independente do fornecedor; credencial
  confinada ao keyring; UI futura protegida de mentiras de estado; fixtures provam
  as regras sem rede.
- Negativas: a semântica externa só pode ser validada com serviço real; o v1 fecha
  campos aditivos.
- Neutras: `SZ-RETROACHIEVEMENTS` permanece `planned`; validação de fixtures é
  evidência de design, não de funcionalidade.
