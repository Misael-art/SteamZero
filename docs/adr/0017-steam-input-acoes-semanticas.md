# ADR-0017 — Steam Input + camada de ações semânticas universais

**Status:** aceito

## Contexto
§10.8. EmuDeck distribui templates de perfil Steam Input por emulador; RetroDECK instala controller layouts; PhaseZero tem hotkey-actions/input-actions. Cada emulador tem hotkeys diferentes — o usuário reaprende N esquemas.

## Alternativas
1. **Vocabulário semântico único (sair, save/load state, pausa, FF, disco, tela, captura, menu desempenho) mapeado por adapter para o mecanismo real de cada emulador (hotkey, CLI, IPC), entregue via templates Steam Input consistentes** (escolhida).
2. Só templates por emulador (EmuDeck-style) — contras: inconsistência entre emuladores permanece.
3. Daemon de input próprio interceptando (uinput) — contras: latência/fragilidade/anticheat-like problemas; usar apenas como fallback pontual e declarado por adapter.

## Decisão
`semanticActions` no adapter.json; perfis por emulador/plataforma/jogo em camadas (CONFIGURATION-SCHEMAS); detecção de conflitos; teste de eixos/botões na UI; recuperação de controle pós-suspensão (F-CT-03).

## Consequências
Matriz por emulador do que é suportável (nem todos expõem tudo — capacidade declarada, UI mostra o disponível).

## Riscos
Steam Input API/formatos mudam (R-03) — templates versionados na Compat Matrix.

## Revisão
Fase 4 após 5 adapters; medir cobertura média do vocabulário.
