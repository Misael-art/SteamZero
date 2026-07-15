# ADR-0004 — Serviço local (daemon por usuário) com CLI in-process como fallback

**Status:** aceito

## Contexto
§9.5 exige serviço local; UI não pode executar shell. PhaseZero-Windows usa re-spawn de processo por seleção (funciona, mas sem progresso rico nem jobs persistentes); RetroDECK tem `api_server.sh` (precedente de daemon no domínio).

## Problema
Jobs longos (conversões, sync) precisam sobreviver à UI; múltiplos clientes (Game Mode, QAM, CLI) precisam da mesma verdade; eventos de progresso precisam de push.

## Alternativas
1. **Daemon por usuário (socket-activated) + CLI capaz de rodar in-process sem daemon** (escolhida).
2. Execução direta por invocação (modelo PhaseZero-WPF) — contras: jobs morrem com a UI; sem event bus; locks entre processos frágeis.
3. Serviço de sistema (root) — contras: viola menor privilégio; desnecessário.

## Prós
Jobs persistem; um único dono do State Store (SQLite writer único); eventos push; QAM/UI/CLI consistentes.

## Contras / Riscos
Mais um processo para diagnosticar (mitigado: doctor, logs estruturados); recovery de crash obrigatório (já exigido pelo modelo transacional).

## Decisão
JSON-RPC 2.0 sobre UNIX socket em `$XDG_RUNTIME_DIR`, systemd user socket activation quando disponível; `steamzero` detecta ausência do daemon e executa in-process com os mesmos contratos (single-shot, sem event push).

## Consequências
LOCAL-API-CONTRACT como fonte de verdade; testes de reconexão/replay; peer credentials + confirmToken (AUTHORIZATION-MODEL).

## Revisão futura
Se SteamOS restringir user services, promover D-Bus activation; revisitar na Fase 2.
