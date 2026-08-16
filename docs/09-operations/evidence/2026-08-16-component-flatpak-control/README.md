# Componente: progresso e cancelamento Flatpak

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base do incremento: `f52a945`

## Hipótese a reproduzir

O executor Flatpak registra rollback durável, porém as operações de até 1.800 s
rodam em `subprocess.run()`. O job não recebe etapas e um pedido de cancelamento
não alcança o processo enquanto ele está ativo.

A prova vermelha deve exigir etapas persistidas, safepoints entre fases e
terminação do processo Flatpak real quando o controle do job pede cancelamento,
sem usar o Flatpak instalado nem alterar o host.
