# ADR-0008 — Decky Loader: adapter QAM opcional, nunca dependência

**Status:** aceito

## Contexto
Decky quebra a cada atualização relevante do Steam Client (histórico público; §11.5 do prompt exige independência). PhaseZero já modela Decky como opt-in (`install-plugins.sh`, `decky-ws-client.py`) — precedente direto.

## Alternativas
1. **QAM via Decky como conveniência opcional; funcionalidade completa por Game Mode UI/CLI/API/hotkeys** (escolhida).
2. Construir a UX principal como plugin Decky — contras: dependência frágil de terceiro não-oficial; lógica no lugar errado.
3. Ignorar QAM totalmente — perde conveniência real (save rápido, perfil) que usuários amam.

## Decisão
Plugin QAM fino (cliente da API com escopo restrito — AUTHORIZATION-MODEL), healthcheck + desativação limpa (FM-11), Compat Matrix registra a tripla {Steam, Decky, plugin}.

## Consequências
Nenhum caminho crítico passa pelo QAM (testado: suíte roda com QAM off).

## Revisão
Se a Valve oficializar API de QAM para apps, migrar o adapter.
