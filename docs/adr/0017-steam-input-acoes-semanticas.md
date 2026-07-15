# ADR-0017 — Steam Input + camada de ações semânticas universais

**Status:** aceito

## Contexto
§10.8. EmuDeck distribui templates de perfil Steam Input por emulador e RetroDECK
instala controller layouts. Cada emulador tem hotkeys diferentes — o usuário reaprende
N esquemas. No Desktop portátil, Steam, KDE e InputPlumber também podem disputar o
mesmo dispositivo.

## Alternativas
1. **Vocabulário semântico único (sair, save/load state, pausa, FF, disco, tela, captura, menu desempenho) mapeado por adapter para o mecanismo real de cada emulador (hotkey, CLI, IPC), entregue via templates Steam Input consistentes** (escolhida).
2. Só templates por emulador (EmuDeck-style) — contras: inconsistência entre emuladores permanece.
3. Daemon de input próprio interceptando (uinput) — rejeitado: latência, fragilidade e
   ownership duplicado. InputPlumber pode ser adapter externo opcional, não código do núcleo.

## Decisão
`semanticActions` no adapter.json; perfis por emulador/plataforma/jogo em camadas;
detecção de conflitos; teste de eixos/botões na UI; recuperação pós-suspensão. No
Desktop, somente um owner fica ativo entre `kde-shortcuts`, `steam-input` e
`inputplumber`. InputPlumber só é elegível após validação explícita no hardware; estar
instalado não basta. Owner ausente degrada para controles físicos, nunca inicia dois.

## Consequências
Matriz por emulador do que é suportável (nem todos expõem tudo — capacidade declarada, UI mostra o disponível).

## Riscos
Steam Input/InputPlumber mudam e podem cair (R-03) — adapters versionados, timeout,
modo observador e modo seguro cobrem a perda.

## Revisão
Fase 4 após 5 adapters; medir cobertura média do vocabulário.
