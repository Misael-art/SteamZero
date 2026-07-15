# ADR-0001 — Núcleo em Python; Bash apenas como shim

**Status:** aceito (Fase 0) · **Decide:** Bash × Python para núcleo/domínio/adapters

## Contexto
PhaseZero linux/ mistura Bash (128 scripts) e Python (library pipeline, frontends, media); a duplicação shell↔python já apareceu lá (frontends.sh+.py, heroic.sh+.py). EmuDeck é 100% Bash sem strict mode; RetroDECK é Bash com eval; LinuxToys é Python GUI + Bash scripts.

## Problema
Transações com journal, State Store SQLite, JSON-RPC, máquinas de estado e parsers estruturados exigem tipos, testes e tratamento de erro que Bash não oferece com segurança auditável.

## Alternativas
1. **Python núcleo + shims Bash mínimos** (escolhida)
2. Bash "endurecido" em tudo — prós: proximidade dos fontes; contras: eval-free dispatch difícil, sem tipos, parsing frágil, testes caros; risco: repetir a classe de bugs do EmuDeck/RetroDECK.
3. Rust/Go núcleo — prós: robustez/velocidade; contras: barreira de contribuição para o ecossistema (todo o domínio de referência é Bash/Python), iteração mais lenta; risco: reescrever conhecimento em linguagem que a comunidade emu-Linux não revisa.

## Prós
Reuso conceitual direto do melhor código existente (library pipeline PhaseZero é Python); pytest/hypothesis; pydantic/jsonschema; sqlite3 stdlib; empacota bem em Flatpak.

## Contras / Riscos
Startup do interpretador (mitigar: daemon persistente); performance de hash em massa (mitigar: bibliotecas nativas, I/O-bound de qualquer forma — benchmark M7).

## Decisão
Python 3.11+ para daemon, CLI, domínio, adapters e helper client. Bash somente onde inevitável (hooks de sessão do SteamOS, wrappers de launch), sempre `set -euo pipefail` + shellcheck, sem lógica de domínio.

## Consequências
Lints de fronteira (MODULE-BOUNDARIES) em Python; contratação/contribuição orientada a Python; shims listados e auditados individualmente.

## Revisão futura
Se benchmark M7 falhar em Deck (scan 10k > alvo) ⇒ reavaliar extensões nativas (Rust module) pontuais, não o núcleo.
