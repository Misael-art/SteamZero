# Componente: terminalização de planos

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base do incremento: `d2553b1`

## Hipótese a reproduzir

O job termina como `rolled-back` ou `cancelled`, mas o plano de componente e os
planos delegados permanecem `pending`. Isso permite que histórico terminal
aponte para autorização ainda reutilizável e faz o retry repetir o mesmo plano,
em vez de criar uma tentativa nova e auditável.

A correção deve terminalizar sucesso, falha, cancelamento, expiração e recovery;
um retry deve criar outro `planId`, manter a correlação com a tentativa anterior
e nunca recolocar um plano terminal em `pending`.
