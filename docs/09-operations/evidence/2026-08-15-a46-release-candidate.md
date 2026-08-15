# Evidência operacional — candidata a46 harmonizada

Data: 2026-08-15  
Branch: `codex/harmonize-ui-g45-release-candidate`  
Commit de código instalado: `a02dae5f60acd6bc2df50fee462f2134b8891f47`  
Release ativa: `0.1.0a46-a02dae5f60ac`  
Rollback disponível: `0.1.0a46-40aa9bafa062`

## Cadeia de suprimentos e gates

- CI push `31910636599`: sucesso em Python 3.11, 3.12 e 3.14, wheel/smoke/supply chain, gate visual QML, Ubuntu 24.04, Arch e Manjaro.
- CI pull request `31910639121`: a mesma matriz concluiu com sucesso no mesmo SHA.
- Wheel SHA-256: `e913b2e6a566815d6620617a7df06ee94463ba6f90e01e76a25738c369779858`.
- Suíte local isolada, com árvore parada: `4692 passed, 10 skipped` em 975,20 s; fingerprint do estado real idêntico antes e depois.
- Ruff, `ruff format --check`, mypy (222 arquivos), independência, fronteiras, status e `diff --check`: aprovados.

## Ativação transacional

O plano validou CI verde, bundle, checksums, schema 20, ownership, espaço,
daemon, units e rollback antes da autorização. A ativação concluiu com:

- `deploymentHealthy=true`;
- `physicalCertification=false`;
- daemon reiniciado e identificado no commit/release exatos;
- primeira convergência aprovada e segunda convergência idempotente;
- doctor sem blockers, integridade do `state.db` aprovada, zero operações pendentes e zero jobs travados;
- serviço `steamzero-core.service` e socket `steamzero-core.socket` ativos;
- Game Mode em estado `ready`;
- QML offscreen permaneceu vivo durante a janela de cinco segundos;
- fingerprint transacional confirmou `statePreserved=true`.

O journal terminou em `committed`, com `smokes-passed`, release corrente
`0.1.0a46-a02dae5f60ac` e nenhuma fase de rollback.

## Provas adicionais na release instalada

- `steamzero service status --json`: `converged`, daemon no SHA exato, sem restart adicional.
- `steamzero doctor --json`: proveniência, geração do serviço, layout e integridade do banco aprovados.
- UI instalada aberta com backend offscreen/software: permaneceu viva por oito segundos e foi encerrada pelo timeout esperado (`124`), sem stderr.
- Temas builtin listados e tema padrão resolvido com alvos mínimos de 48 px.
- Workspace de emulação, jobs, operações e frontends responderam pela bridge real sem mutação.
- Recursos degradaram honestamente por leitura parcial de `/proc`; o daemon permaneceu atribuível e ativo.

A sonda `admin health` foi interrompida antes de seu timeout Polkit de 90 s para
não manter uma autorização gráfica desnecessária. Doctor, identidade do daemon e
units já forneciam a prova read-only exigida; nenhuma conclusão de saúde foi
atribuída a essa sonda interrompida.

## Recuperação e limites

Duas candidatas anteriores reprovaram depois da ativação e restauraram/verificaram
automaticamente `0.1.0a46-40aa9bafa062`. A segunda preservou a causa estruturada
`E-HOST-CURRENT-UNREADABLE`, que levou à correção do smoke pré-convergência.

O comando legado de ciclo completo recusou a candidata porque a proveniência não
pertence a `refs/heads/main`. A recusa ocorreu antes de mutação e não foi
contornada. Assim, há prova real de rollback automático e de roll-forward
saudável, mas não há alegação de `machineCycle=passed` para este SHA.

O doctor registra dois avisos não bloqueantes: um backup órfão preexistente e
estado de boot direto `unknown` por falta de permissão de inspeção. Não houve
limpeza, varredura de raiz, abertura de jogo, instalação de emulador, alteração
de credencial, reboot, merge, tag ou publicação.

## Bloqueio de publicação

A PR #81 descende da PR #80 e, por consequência, contém também #79 e #78.
Mesclá-la colocaria toda a G45 em `main`. A PR permanece em rascunho e não deve
ser mesclada até o operador aprovar, nesta release e neste SHA, boot físico,
controle, foco, Game Mode, retorno ao desktop e fallback. Só depois dessa prova
pode existir certificação, tag ou publicação.
