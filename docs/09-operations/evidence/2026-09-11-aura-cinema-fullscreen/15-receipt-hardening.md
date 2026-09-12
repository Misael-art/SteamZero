# Revisão da retomada — 2026-09-12

Base conferida: `3e39d7105b4f72bd0ee24e9fb52dc91549e37c13`, tip remoto
de main e merge da PR #153. CI main `34678074389`: success.
Branch de correção: `codex/aura-receipt-hardening-2026-09-12`.
Commit funcional: `1f855058a7a524ccca5048047ffa3f32acd024e6`.

Release observada por readlink: `2.0.0rc1-9caa2c223cfb`.
Nenhuma instalação ou mutação da sessão KDE nesta revisão.

## Reprodução e correção local

Dois testes novos falharam antes da alteração:

- `test_partial_reply_reports_delay_and_later_confirms`: um subprocesso
  escreve `{`, faz flush e espera. O seletor detecta bytes, mas readline
  bloqueia até newline/EOF; o timeout não promove pending para delayed.
- `test_non_object_error_is_malformed_without_worker_exception`: error string
  causa AttributeError em vez de resultado unconfirmed/malformed.

Correção local: leitura não bloqueante incremental, prazo monotônico para
respostas parciais, limite de bytes, validação do tipo de error e drenagem
descartável após o recibo para que stdout cheio não bloqueie o filho.
Não há kill do processo, nem liberação de lançamento por timeout.

A revisão da ponte também reproduziu que uma sessão canônica nova do mesmo
jogo, mas com `sessionId` diferente daquele confirmado pelo recibo, era aceita
como pertencente ao pedido. O teste negativo falhou (`running` em vez de
`awaiting`). A ponte agora só vincula a observação quando o recibo está
`confirmed` e os dois `sessionId` são idênticos; `pending`, `delayed`,
`unconfirmed` e sessão divergente permanecem bloqueados em `awaiting`.

Testes adicionais cobrem saída volumosa após confirmação e recibo acima do
limite. Comando executado:

```text
PYTHONPATH=src /mnt/sdcard/Projects/Port_Steam/.venv/bin/python tools/run_tests_isolated.py tests/integration/test_launcher_receipt.py tests/integration/test_launcher_app.py tests/integration/test_launcher_session_observation.py -q
```

Resultado: **38 passed em 10,19 s**, fingerprints do estado real iguais antes
e depois. São processos sintéticos e testes de integração; não jogo físico.

## Pendências antes de promover

- Gate integral executado em unidade transitória de usuário para sobreviver ao
  limite do terminal: **5.957 passed, 47 skipped, 1 failed em 35m12s**. A única
  falha foi `test_committed_catalog_and_generated_views_are_consistent`, pois
  os próprios `16-receipt-hardening-gates.log/xml` nasceram dentro do diretório
  coberto pelo digest durante a execução. Todos os testes funcionais passaram e
  o fingerprint do estado real foi idêntico antes/depois. A visão será
  regenerada; `tests/unit/test_project_status.py`: **10 passed** e
  `status-check`: **OK**, ambos após o nascimento dos artefatos.
- Gates estáticos verdes na composição: Ruff check; Ruff format check
  (**602 arquivos**); Mypy (**271 arquivos**); independência e fronteiras
  (**0 violações**).
- Push, CI e integração do commit funcional isolado.
- Instalação governada com rollback, seguida de erro/retry e jogo/retorno com
  PNGs da release efetivamente instalada.
- Desconexão da ponte, Steam, OSD/saves e desempenho físico seguem abertos.

Este registro não certifica o Launcher nem a Theme Engine.
