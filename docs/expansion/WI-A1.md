# WI-A1 — Playtime, sessões interrompidas e continuar jogando

## Entrega

- a migração v13 evolui `game_session` com segundos jogados e origem explícita
  da medição, preservando o lifecycle canônico;
- sessões existentes encerradas recebem backfill transparente por relógio de
  parede; nenhum dado legado é promovido a medição monotônica;
- o wrapper Steam mede o processo acompanhado com relógio monotônico e recovery
  pós-crash grava aproximação `recovered-wall-clock`;
- o Session Manager soma somente intervalos em execução, excluindo o período
  suspenso;
- lançamentos emulados reais criam sessão antes do spawn, registram PID
  observado e usam watcher `waitpid` para fechamento ou interrupção;
- `feat-playtime-v1` agrega tempo, contagem de sessões, recentes, última sessão,
  origem e ação segura com paginação keyset opaca;
- CLI e daemon publicam `playtime list|show`;
- o dashboard entrega o read model à Home QML, que mostra até quatro jogos,
  tempo total, estado textual e alvos de pelo menos 48×48;
- continuar um jogo usa somente AppID Steam numérico ou o launcher de emulação
  já allowlisted.

## Sessões interrompidas

- PID vivo isoladamente não é tratado como ownership;
- sessão Steam ativa e não observável vira ação “Recuperar sessão”; o primeiro
  gesto apenas encerra o registro órfão com `E-SESSION-INTERRUPTED`;
- depois do recovery, uma atualização oferece “Continuar”;
- watcher de emulação que perde o filho registra a sessão como interrompida;
- sessão legada sem origem de launcher permanece informativa e desabilitada.

## Segurança e privacidade

- o contrato público não contém PID, argv, ambiente ou paths internos;
- `gameId`, cursores, limites e flags são fechados e limitados;
- URLs Steam são construídas internamente como `steam://rungameid/<AppID>` após
  validação exclusivamente numérica;
- o read model não muta estado e nunca tenta recuperar silenciosamente;
- falha do provider de playtime degrada apenas a seção correspondente.

## Evidência

- suíte integral: 1394 testes aprovados;
- cobertura limpa: 85,24% (mínimo exigido: 85%); domínio de playtime: 87,20%;
- Hypothesis executa 50 exemplos contra o cursor e aceita somente página válida
  ou erro tipado;
- migração v12→v13, backfill, paginação, medição, suspensão, watcher, recovery,
  CLI, JSON-RPC e bridge possuem testes dedicados;
- QML offscreen aprovado em 949×593 e 1280×800, incluindo card recente e alvo
  mínimo;
- Ruff, mypy strict em 146 módulos, independência e fronteiras: aprovados.

Estado final: `verified-dev`. Não há alegação de ergonomia física, precisão de
playtime legado ou validação em hardware real.
