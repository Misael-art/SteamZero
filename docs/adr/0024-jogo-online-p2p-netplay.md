# ADR-0024 — Jogo online P2P: contrato interno de sessão e netplay

**Status:** aceito

## Contexto

O item `SZ-ONLINE-P2P` planeja jogo online ponto a ponto ("netplay") como capacidade
futura, sem emulador ou serviço externo escolhido. Antes de qualquer implementação é
preciso fixar o contrato interno de sessão: quem participa, como se convida, o que é
comparado entre os lados, como o transporte cai de modo e como a privacidade é
preservada. Este ADR define esse contrato e o valida com fixtures. Não escolhe
emulador, não define matchmaking público e não implementa runtime.

## Objetivo e não objetivos

**Objetivos**

- Definir o modelo de sessão, estados, compatibilidade, transporte, segurança,
  sincronização e privacidade de uma sessão P2P privada.
- Separar explicitamente as capacidades vizinhas para que nenhuma seja tratada como
  equivalente a netplay.
- Entregar um envelope JSON normativo (`netplay-session-v1`) com fixtures válidas e
  inválidas que servem de contrato para futuros agentes.

**Não objetivos**

- Escolher emulador, serviço de matchmaking, fornecedor de relay ou pilha de
  transporte (WebRTC, libp2p etc.).
- Implementar rede, NAT, relay, daemon, banco, CLI ou UI.
- Transferir ROM, save ou arquivo de jogo entre peers.
- Abertura de portas no host, encaminhamento permanente ou serviço público.
- Matchmaking público, ranking, lobby ou busca de partidas. Convite privado apenas.

## Vocabulário

| Termo | Significado |
|---|---|
| sessão | unidade de jogo online; tem `sessionId`, estados e dono (host). |
| host | participante que criou a sessão e negocia a sincronização. |
| guest | participante convidado. |
| convite | token opaco, expirável e single-use que autoriza um participante. |
| compatibilidade | conjunto de verificações comparadas entre os lados antes de conectar. |
| transporte | caminho de dados entre os peers: `direct` ou `relay`. |
| sync | estado de sincronização: host, ordem de entrada, divergência, latência. |
| netplay | jogar o mesmo jogo de forma sincronizada entre dois ou mais participantes. |

## Atores e limites de confiança

| Ator | Confia em | Não confia em |
|---|---|---|
| host | si mesmo; no convite que emitiu | no guest até autenticação mútua e compatibilidade verificadas |
| guest | si mesmo; na sessão convidada | no host além do contrato; nunca envia ROM |
| relay | apenas encaminhar bytes e metadados mínimos | conteúdo dos pacotes; não é o dono da sessão |
| operador | dados locais | nenhum participante remoto, relay ou serviço externo |

O relay nunca vê o conteúdo da sessão (criptografia de ponta a ponta), e nenhum
participante vê a ROM do outro.

## Modelo de sessão e estados

Estados do envelope `netplay-session-v1`:

| Estado | Significado | É terminal? |
|---|---|---|
| `created` | sessão criada, aguardando convite | não |
| `inviting` | convite emitido, aguardando aceite | não |
| `negotiating` | troca de capacidades entre os lados | não |
| `compatibility-check` | verificações de compatibilidade em andamento | não |
| `connecting` | transporte sendo estabelecido | não |
| `active` | jogo sincronizado em andamento | não |
| `reconnecting` | transporte caiu e está sendo restabelecido | não |
| `ended` | encerramento normal | sim |
| `failed` | falha terminal com `error` obrigatório | sim |
| `cancelled` | cancelamento antes de conectar | sim |

Transições obrigatórias:

- `created → inviting → negotiating → compatibility-check → connecting → active`;
- `connecting → reconnecting → active | failed`;
- qualquer estado não terminal → `cancelled` | `failed` | `ended`;
- `ended`, `failed` e `cancelled` não transicionam (terminal).

O envelope exige `error` quando `state == "failed"` e proíbe `error` em qualquer outro
estado. Sessões `active` exigem `sync`; estados de conexão (`connecting`, `active`,
`reconnecting`) exigem `invitation` aceito e `transport`.

## Compatibilidade obrigatória

A comparação entre os lados acontece em `compatibility.checks`, cada check com
`kind` e `result` (`pass`/`fail`/`unknown`). Kinds obrigatórios:

| Check | O que compara | Observação |
|---|---|---|
| `platform` | plataforma do jogo | ex.: `sfc` |
| `game-hash` | `sha256` do jogo | digest local, ROM nunca sai da máquina |
| `core` | core/emulador | id estável do core |
| `core-version` | versão do core | semver exato `M.N.P` |
| `save-state` | versão de save/state | quando aplicável |
| `deterministic-config` | seed e clock | configuração determinística relevante |
| `player-count` | número de jogadores | 2..8 |
| `control-profile` | perfil de controles | semântico, não bind de teclas |
| `region` | região/timing | ex.: `ntsc-u` |

Regras contratuais: qualquer check `fail` obriga `status == "incompatible"`;
`unknown` não bloqueia, mas não autoriza `active`. Rollback/lockstep são negociados
via `sync.rollbackCapable`/`sync.lockstepCapable`, nunca presumidos.

## Transporte

1. **Tentativa direta primeiro.** `transport.mode == "direct"` é o caminho preferido.
2. **Descoberta de NAT** informativa (`natDiscovered`), nunca abertura automática de
   porta permanente no host.
3. **Relay opcional.** `mode == "relay"` exige `relayId` opaco; relay sem id é
   `RELAY_UNAVAILABLE`.
4. **Fallback** direto → relay em tentativas limitadas (`attemptCount` 1..5).
5. **Timeouts limitados** (`timeoutMs` 100..30000).
6. **Migração de rede** sinalizada por `transport.networkChanged` durante
   `reconnecting`.
7. **Reconnect** progressivo; `active` só é retomado após nova compatibilidade
   implícita da mesma sessão.
8. **Cancelamento** a qualquer momento antes de `active`; `ended` após encerramento
   limpo.

## Segurança

- **Convite opaco e expirável**: token aleatório `inv-*`, `expiresAt` obrigatório,
  single-use (`usedCount` máximo 1).
- **Autenticação mútua** antes de `connecting`; a sessão privada só existe a partir
  de convite aceito.
- **Consentimento de cada participante**: host cria e convida; guest aceita; ninguém
  entra sem os dois lados.
- **Proteção contra replay**: convite single-use + estados terminais irreversíveis;
  repetir um convite usado é `INVITE_REUSED`.
- **Limitação de tentativas**: `attemptCount` máximo 5; excedente vira
  `TOO_MANY_ATTEMPTS`.
- **Bloqueio/revogação**: convite pode ser `revoked` pelo host; sessão então
  `cancelled` (ou `failed`).
- **Nenhum encaminhamento de arquivo de jogo**: o envelope não admite caminho, dump
  ou hash que revele conteúdo além do digest.
- **Nenhuma abertura automática de porta permanente** no host.

## Sincronização

- **Negociação de host**: `sync.hostPeerId` é imutável após `active`.
- **Ordem de entrada**: `sync.inputOrder` lista os peers na ordem definida na
  negociação; única ordem válida.
- **Divergência**: `sync.divergenceMs` (0..5000) mede a diferença entre os peers;
  negativa é inválida (fixture `10-sync-divergence`).
- **Atraso**: `sync.latencyMs` observado, nunca prometido.
- **Abandono**: `sync.abandoned == true` obriga estado terminal (`failed`/`ended`/
  `cancelled`).
- **Host perdido**: `HOST_LOST` encerra a sessão em `failed` com causa registrada;
  sem eleição de host novo no v1.
- **Retomada ou encerramento seguro**: `reconnecting` preserva a sessão; excedido o
  limite de tentativas, encerra em `failed` com `error.retryable`.

## Privacidade e retenção

- **O que o peer vê** (`privacy.peerVisible`): apenas `displayName`, `latencyMs`,
  `region`, `platformId` — nunca caminhos, digests parciais ou conteúdo.
- **O que o relay vê** (`privacy.relayVisible`): apenas `sessionId`, `byteVolume`,
  `durationMs` — nunca payload, nome de jogo ou identidade real.
- **Retenção mínima**: snapshots de sessão retidos localmente somente para
  diagnóstico; `ended`/`failed`/`cancelled` podem ser purgados após a janela
  definida pelo estado do produto.
- **Logs**: sem tokens, sem digests de ROM fora do fluxo de compatibilidade, sem
  IP público do operador.
- **Redaction**: qualquer serialização persistida aplica redaction antes de
  escrever (mesma regra dos demais contratos do produto).

## Versionamento do contrato

- `schemaVersion` fixo em `1`; mensagens com outra versão são rejeitadas
  (`FUTURE_PROTOCOL_VERSION`).
- Novos campos só entram em `v2` com negociação explícita; um peer v1 nunca
  interpreta campos de v2 (envelope fechado `additionalProperties: false`).

## Identificadores e idempotência

- `sessionId`: `np-<8 hex>-<4 hex>`, determinístico nas fixtures.
- `peer-*`: identidade de participante dentro da sessão.
- `inv-*`: token de convite, gerado uma única vez; reutilização é erro.
- `relay-*`: identidade opaca do relay.
- Sessão é idempotente por `sessionId`: reaplicar o mesmo snapshot não altera
  estado terminal.

## Timestamps

Todos em UTC, RFC 3339 com sufixo `Z` (`format: date-time` + `pattern: Z$`). Nenhum
timestamp local, offset ou relativo entra no envelope.

## Códigos de erro estáveis

`error.code` é enum fechado: `VERSION_INCOMPATIBLE`, `GAME_HASH_INCOMPATIBLE`,
`CORE_INCOMPATIBLE`, `INVITE_EXPIRED`, `INVITE_REUSED`,
`PARTICIPANT_NOT_AUTHORIZED`, `TOO_MANY_ATTEMPTS`, `RELAY_UNAVAILABLE`,
`PEER_DISCONNECTED`, `SYNC_DIVERGENCE`, `FUTURE_PROTOCOL_VERSION`,
`SENSITIVE_PAYLOAD_REJECTED`, `NAT_FAILED`, `TIMEOUT`, `HOST_LOST`.
`error.retryable` indica se o fluxo pode tentar de novo; código nunca é reutilizado
com outro significado.

## Cancelamento e teardown

Cancelar antes de `active` move a sessão para `cancelled` (convite `revoked`).
Encerrar durante `active` faz teardown ordeiro: parar entrada, drenar sync,
desconectar transporte e então `ended`. Nenhum recurso de rede permanece aberto após
estado terminal.

## Comportamento offline

O jogo local nunca depende da sessão online: falha de netplay degrada para o modo
local preservado (mesma regra de `SZ-EMULATION-M10`). Sessão online offline não é
possível; tentativa é `TIMEOUT`/`RELAY_UNAVAILABLE` com jogo local intacto.

## Rate limit e defesa contra abuso

- `attemptCount` limitado a 5 por sessão.
- Convite expira em tempo finito (`expiresAt` obrigatório).
- Sem matchmaking público, sem descoberta global: convite é o único caminho de
  entrada, o que limita superfície de abuso.
- Relay com teto de volume/deduplicação (detalhes na implementação do relay,
  adiados).

## Recuperação após queda

Queda do processo do host: sessão persiste em estado conhecido (`connecting`/
`active`/`reconnecting`) e o guest observa `PEER_DISCONNECTED`/`HOST_LOST`; a
retomada automática fica para o runtime futuro. Quesito: nenhuma tela preta, o jogo
local continua jogável com causa registrada no status.

## Observabilidade

Permitido: `sessionId`, estados, `error.code`, `transport.mode`, `attemptCount`,
latência observada. Proibido em logs persistidos: token de convite, digest de ROM,
IPs reais, conteúdo de pacote, identidade real do participante.

## Critérios para promover de `planned` para `verified-dev`

- Envelope e fixtures validados por teste contratual (evidência de design, não de
  funcionalidade).
- Porta/serviço de sessão no runtime capaz de produzir e consumir o envelope v1.
- Ciclo mínimo verificado em ambiente isolado: criar → convidar → compatível →
  conectar (loopback ou VM, sem host real).
- Falha degradada verificada: relay indisponível e timeout terminam com jogo local
  utilizável.

## Fronteiras com outras capacidades

| Capacidade | Relação com P2P |
|---|---|
| streaming/cast remoto | transporta vídeo e áudio; P2P não transporta mídia (ver ADR-0026) |
| Remote Play | extensão de jogo para outro dispositivo; P2P é dois jogadores, mesma máquina lógica |
| compartilhamento de tela | espelha a tela; P2P sincroniza estado do jogo, não pixels |
| retorno de gamepad | input via `inputOrder` sincronizado; não é "controle remoto" |
| matchmaking público | não objetivo; convite privado apenas |
| convite privado | mecanismo de entrada da sessão P2P |

## Dependências futuras de runtime

Antes de implementar netplay o runtime precisa de:

1. porta de sessão P2P (criação, convite, estados) em `steamzero.ports`;
2. serviço de transporte com `direct`/`relay` abstraído (negociação de NAT,
   reconnect, timeouts) — fornecedor ainda por escolher;
3. serviço de compatibilidade que compara os checks do envelope;
4. suporte a `sync` de entrada (rollback ou lockstep) delegado ao core do emulador;
5. keyring/identidade local para autenticação mútua (compartilhado com ADR-0025);
6. integração com o estado do produto para `unknown`/`permissionDenied` em `status()`.

Nada disso é implementado por este ADR.

## Decisões adiadas e perguntas em aberto

- Fornecedor do transporte (WebRTC vs. libp2p vs. protocolo próprio).
- Fornecedor/operador do relay e política de teto de banda.
- Suporte a 3+ jogadores (o envelope suporta até 8, mas o fluxo v1 é 2).
- Migração de host (`HOST_LOST` encerra; eleição fica adiada).
- Política de retenção exata de snapshots (prazo em horas/dias).
- Pesquisa oficial necessária: comportamento de cores populares com rollback
  (não documentar como fato sem fonte).

## Consequências

- Positivas: contrato testável antes de qualquer implementação; fronteiras claras
  entre netplay, streaming e Remote Play; falha degrada sem travar o jogo local.
- Negativas: o contrato fecha o v1 (campos aditivos exigem v2 negociado); a escolha
  do transporte fica pendente.
- Neutras: `SZ-ONLINE-P2P` permanece `planned`; fixtures são evidência de design.
