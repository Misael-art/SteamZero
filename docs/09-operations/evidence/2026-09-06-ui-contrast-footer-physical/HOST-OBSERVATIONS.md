# Observações do host

## Baseline

`release_host.py --json inspect` confirmou a release ativa
`2.0.0rc1-d556f7f5c89b`, com serviço e socket ativos e zero operações
pendentes. A janela fotografada foi iniciada pelo próprio agente e identificada
por PID antes da captura; a janela do Launcher do usuário não foi tocada.

## Ativação concluída

O plano governado para `2.0.0rc1-3cb57f4c1d59` passou bundle, CI, preflight e
rollback. A retomada autenticada ativou a release, confirmou convergência na
primeira chamada e `restarted:false` na segunda, com `pendingOperations=0`.
O rollback disponível é `2.0.0rc1-d556f7f5c89b`. A sessão KDE não foi
reiniciada nem encerrada.
