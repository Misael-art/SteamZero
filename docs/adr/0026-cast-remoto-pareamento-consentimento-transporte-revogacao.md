# ADR-0026 — Cast remoto pela internet: pareamento, consentimento, transporte e revogação

**Status:** aceito

## Contexto

O item `SZ-CAST-INTERNET` planeja cast da tela/jogo do SteamZero para dispositivos
remotos pela internet. Os ADRs 0022 (compartilhamento de tela multi-provedor) e 0023
(receptor web) definem o cast em LAN com `screen-cast-v1`. Este ADR estende o mesmo
conceito para WAN, onde aparecem dimensões que a LAN não exige: pareamento por código
ou QR, consentimento explícito e revogável, NAT/relay, autenticação de sessão e
permissões granulares. O contrato é novo e próprio (`remote-cast-session-v1`), porque
WAN adiciona requisitos que o envelope de LAN não representa; nada aqui implementa
runtime nem documenta endpoints externos como fatos sem fonte oficial.

## Objetivo e não objetivos

**Objetivos**

- Definir estados de sessão de cast remoto e suas regras;
- definir pareamento expirável com tentativas limitadas e vinculação de dispositivo;
- definir consentimento bilateral (emissor e receptor) com permissões granulares;
- definir transporte direto/NAT/relay, trocas de rota, degradação e teardown;
- definir segurança de sessão (autenticação, confidencialidade, integridade,
  rotação de material, revogação imediata) e fail-safe local.

**Não objetivos**

- Implementar adapter, relay, TURN/STUN, negociação WebRTC ou receptor web;
- documentar protocolos proprietários de terceiros;
- enviar clipboard, arquivos, SDP integral, IP público ou candidatos ICE em
  payloads persistidos;
- definir o cast em LAN, que permanece sob os ADRs 0022/0023 e `screen-cast-v1`.

## Relação com o cast em LAN

`screen-cast-v1` continua sendo o contrato de cast local multi-provedor. O cast
remoto é uma evolução conceitual para WAN: reusa a ideia de provedor/sessão, mas o
envelope `remote-cast-session-v1` é separado porque carrega pareamento, consentimento
bilateral, autenticação e transporte WAN. Um mesmo jogo pode ser emitido em LAN e em
WAN; as duas superfícies não dependem uma da outra.

## Estados da sessão

| Estado | Significado |
|---|---|
| `idle` | sem pareamento ativo; nada em trânsito |
| `pairing` | código/QR emitido, aguardando o receptor |
| `awaiting-consent` | pareado; aguardando consentimento explícito |
| `negotiating` | consentido; negociando transporte e segurança |
| `direct` | mídia fluindo por conexão direta/NAT |
| `relayed` | mídia fluindo via relay |
| `degraded` | mídia ativa com qualidade reduzida |
| `reconnecting` | reconectando após perda/mudança de rede |
| `stopped` | encerrado limpo (teardown) |
| `revoked` | revogado (consentimento ou segurança encerrou tudo) |
| `failed` | falha com `error` obrigatório |

Regras: estados de mídia (`direct`, `relayed`, `degraded`, `reconnecting`) exigem
transporte, qualidade e autenticação estabelecida; `degraded` exige `degradation`;
`reconnecting` exige `transport.lastSwitch`; `stopped` exige `transport.teardown`;
`revoked` exige `consent.revoked`; `failed` exige `error`; `error` só existe em
`failed`.

## Pareamento

- Modos: código de 6 caracteres (`[A-Z0-9]{6}`) ou QR (com `qrToken`).
- **Expiração**: `expiresAt` obrigatório; código vencido vira `PAIRING_EXPIRED`.
- **Tentativas limitadas**: `attemptsRemaining` 0..5; zerado, a sessão deve ser
  `failed` com `TOO_MANY_ATTEMPTS` (proteção contra brute force).
- **Vinculação de dispositivo**: `deviceBound`/`boundDeviceId` fixam o receptor
  após o primeiro pareamento bem-sucedido.
- **Proteção contra replay**: código de uso único e expirável; nova sessão exige
  novo pareamento; sessões são isoladas entre si (`sessionId` único).
- Nenhum endpoint permanente fica exposto publicamente no host.

## Consentimento

- Bilateral: `grantedByEmitter` e `grantedByReceiver`; estados de mídia exigem
  ambos `true`. Ausência de um dos lados impede o fluxo (`CONSENT_DENIED`).
- **Permissões granulares**: `video`, `audio`, `input`, `remoteControl`.
- **Padrões de segurança**: `clipboard` e `files` são `const false` — proibidos no
  v1, mesmo sob elevação; `input` é `false` por padrão e exige
  `consent.explicitInputGrant` para virar `true`; `remoteControl` idem
  (desabilitado por padrão).
- **Elevação exige novo consentimento**: `permissions.elevated: true` exige
  `consent.elevation.granted: true` com `grantedAt` — elevação nunca é herdada de
  um consentimento anterior.
- **Revogação imediata**: `consent.revoked` encerra mídia e input; a sessão vai
  para `revoked` (ou `stopped` quando o encerramento é limpo).

## Transporte

- Modos: `direct`, `nat-traversal`, `relay`.
- Endpoints: `remoteEndpointRef` (referência não persistida, sem IP), `relayId` e
  `region`; `encrypted` é `const true` em toda rota.
- Trocas de rota: `lastSwitch` com `from`/`to`/`at`/`reason`
  (`direct-to-relay`, `relay-to-direct`, `network-change`, `loss`).
- Qualidade adaptativa: `quality.bitrateKbps` (atual), `ceilingKbps` (teto de
  banda), `latencyMs` e `keyframeRequested` (pedido de keyframe).
- Teardown: `transport.teardown.reason` (`user-ended`, `session-ended`, `timeout`).

## Segurança da sessão

- **Autenticação**: `auth.established` obrigatório nos estados de mídia.
- **Confidencialidade e integridade**: cipher fechado (`aes-256-gcm`,
  `chacha20-poly1305`) e tráfego sempre criptografado (`encrypted: true`).
- **Relay não confiável**: relay vê tráfego criptografado e metadados mínimos;
  nenhum segredo de sessão transita em claro por ele.
- **Revogação imediata**: `auth.revoked` exige status `revoked` ou `stopped`;
  revogação derruba mídia e input de uma vez.
- **Rotação de material**: `auth.keyRotation.rotations` e `lastRotatedAt`;
  material de sessão é rotacionado e nunca reutilizado entre sessões.
- **Isolamento entre sessões**: `sessionId` único por sessão; sessão nova exige
  pareamento novo.
- **Sem listener público permanente**: o host não mantém porta aberta para
  receber cast; conexões entram por pareamento/negociação.

## Fail-safe local (falha degrada, nunca trava)

1. Falha do cast **nunca bloqueia o jogo local**; o jogo continua rodando.
2. Input remoto é interrompido primeiro (`degradation.impact: input`); mídia pode
   continuar ou cair depois.
3. Revogação encerra mídia e input simultaneamente, com estado registrado.
4. A UI local permanece utilizável em qualquer estado (`unknown`/`failed` com
   causa registrada).
5. Cleanup remove sessão, socket, processo e autorizações temporárias; nada
   fica escutando após `stopped`/`revoked`/`failed`.

## Observabilidade

Permitido em logs persistidos: `sessionId` (fictício), `status`, `phase`, modo
`direct`/`relay`, `quality`, `degradation.reason`/`impact`, permissões concedidas.
Proibido: credenciais, token de sessão, SDP integral, IP público, candidatos ICE,
chaves, payload de mídia. O envelope v1 não tem campo para esses dados
(`additionalProperties: false`); a fixture `14-sensitive-payload` prova a rejeição.

## Versionamento do contrato

`schemaVersion` fixo em `1`; envelope fechado; campos futuros exigem `v2`
(`13-future-unknown-fields`).

## Códigos de erro estáveis

`PAIRING_EXPIRED`, `TOO_MANY_ATTEMPTS`, `CONSENT_DENIED`, `CONSENT_EXPIRED`,
`AUTH_FAILED`, `RELAY_UNAVAILABLE`, `CONNECTION_LOST`, `NEGOTIATION_FAILED`,
`REVOKED`, `ELEVATION_REQUIRED`, `FUTURE_PROTOCOL_FIELDS`,
`SENSITIVE_PAYLOAD_REJECTED`.

## Identificadores

`sessão`: `rc-sess-<16 hex>`; `dispositivo`: `rc-dev-<12 hex>`; `relay`:
`rc-relay-<12 hex>`; `qrToken`: `rc-qr-<16 hex>`; endpoint: referência
`ref:rc-endpoint-<12 hex>` (nunca endereço IP). Timestamps UTC RFC 3339 com `Z`.

## Critérios para promover de `planned` para `verified-dev`

- Envelope e fixtures validados por teste contratual (evidência de design).
- Pareamento→consentimento→negociação→mídia exercitados em isolamento com
  endpoint fake; revogação interrompe mídia e input.
- Trocas de rota (direct→relay, network-change) e degradação com motivo
  observável em teste isolado.
- Fail-safe: cast falhando não interrompe o jogo local.
- Nenhuma verificação com rede/relay real sem autorização do operador.

## Decisões adiadas e perguntas em aberto

- Provedor de relay/TURN concreto (fora do escopo documental).
- Semântica de elevação além do v1 (clipboard/arquivos exigem v2 e redação
  própria de consentimento).
- Pesquisa oficial necessária: requisitos reais de relay para WAN (não
  documentar sem fonte oficial).

## Consequências

- Positivas: contrato WAN separado e fechado; segurança por padrão (clipboard/
  arquivos proibidos, input por consentimento explícito); fail-safe local
  garantido por regra; fixtures provam o comportamento sem rede.
- Negativas: v1 não cobre clipboard/arquivos; semântica de relay real fica
  pendente de pesquisa oficial.
- Neutras: `SZ-CAST-INTERNET` permanece `planned`; LAN continua sob 0022/0023.
