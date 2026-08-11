# Fronteiras entre as capacidades P2P, RetroAchievements e cast remoto

Referência: ADR-0024 (P2P/netplay), ADR-0025 (RetroAchievements), ADR-0026
(cast remoto). Os três contratos são independentes: nenhum importa o outro e
nenhum compartilha estado obrigatório.

| Fronteira | P2P/netplay | RetroAchievements | Cast remoto |
|---|---|---|---|
| Transporta vídeo | não necessariamente | não | sim |
| Transporta input | input sincronizado entre peers | não | opcional e consentido |
| Exige ROM no peer | depende do netplay, nunca transfere a ROM | não | não |
| Usa credencial externa | não obrigatoriamente | sim, via keyring | depende do relay |
| Funciona offline | jogo local preservado | fila local (outbox) | sessão remota não |
| Pode usar relay | sim | não aplicável | sim |
| Hardcore interfere | possível restrição (decisão adiada) | sim | deve ser explicitamente decidido |

## Notas por capacidade

**P2P/netplay (ADR-0024, `netplay-session-v1`)**

- Nunca transfere a ROM; compatibilidade é verificada por hash, core, versão e
  configuração determinística.
- Relay é opcional; a sessão pode falhar por `RELAY_UNAVAILABLE` sem degradar o
  jogo local.
- Offline: o jogo local continua; a sessão multiplayer não.

**RetroAchievements (ADR-0025, `achievement-event-v1`)**

- Única das três que exige credencial externa; o token vive no keyring e só
  aparece como `credentialRef`.
- Offline: desbloqueios locais são verdade local; sincronização é melhor esforço
  com outbox idempotente.
- Hardcore afeta o que pode ser desbloqueado/validado; modo normal via
  `degradation` com motivo observável.

**Cast remoto (ADR-0026, `remote-cast-session-v1`)**

- Transporta vídeo e, opcionalmente, input (sempre com consentimento explícito);
  clipboard e arquivos são proibidos no v1.
- Relay é possível e observável (`relayed`, `lastSwitch`); o relay não confia
  no tráfego (criptografia ponta a ponta).
- Offline: sessão remota não existe; o jogo local nunca é bloqueado pelo cast
  (fail-safe).
- Interação com hardcore (ADR-0025) ainda não é decidida: um cast remoto em
  sessão hardcore exige decisão explícita antes de implementação.

## Limites comuns

- Nenhum dos três contratos persiste segredos, caminhos locais, IP público ou
  payload sensível; todos são envelopes fechados (`additionalProperties: false`)
  com `schemaVersion` 1.
- Todos exigem UTC RFC 3339 com `Z`; identificadores são fictícios e
  determinísticos.
- Nenhum deles documenta protocolo proprietário de terceiros como fato; o que
  depende de fonte oficial está marcado como decisão adiada/pesquisa necessária.
