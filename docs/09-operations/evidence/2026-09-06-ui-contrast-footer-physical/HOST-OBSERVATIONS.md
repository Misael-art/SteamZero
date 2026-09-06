# Observações do host

## Baseline

`release_host.py --json inspect` confirmou a release ativa
`2.0.0rc1-d556f7f5c89b`, com serviço e socket ativos e zero operações
pendentes. A janela fotografada foi iniciada pelo próprio agente e identificada
por PID antes da captura; a janela do Launcher do usuário não foi tocada.

## Ativação pendente

O plano governado para `2.0.0rc1-3cb57f4c1d59` passou bundle, CI, preflight e
rollback. Três tentativas chegaram a `install-started` e o Polkit registrou
falha de autenticação; nenhuma ativação parcial foi observada. O próximo passo
é repetir o mesmo token depois que a autenticação gráfica do KDE for atendida,
capturar `02-footer-fixed.png` e então verificar convergência, idempotência e
rollback. A sessão KDE não deve ser reiniciada nem encerrada.
