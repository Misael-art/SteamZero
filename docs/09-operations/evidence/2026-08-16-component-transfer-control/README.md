# Componente: progresso e cancelamento durante aquisição

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base do incremento: `bb5645f`

## Hipótese a reproduzir

O cliente de rede já lê artefatos em chunks, mas o job de componente não recebe
esses bytes nem conecta seu pedido de cancelamento à leitura. Assim o progresso
permanece em `preparing` durante o download e cancelar um job em execução só é
honrado depois que `ComponentLifecycle.apply()` retorna.

Este incremento começa com testes vermelhos que exigem contagem persistida de
bytes declarados e terminalização `cancelled` antes de o restante do artefato ou
qualquer operação ser aplicado.
