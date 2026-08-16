# Componente: recovery e retomada após reinício

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base do incremento: `e819bec`

## Hipótese a reproduzir

O job é persistido, mas um novo `ComponentJobService` ainda não reconcilia jobs
`running` sem worker nem retoma jobs `queued` autorizados. A prova vermelha deve
mostrar que o estado pode permanecer não terminal após a perda do processo.

O recovery precisa ser seletivo para `component.apply`: não pode terminalizar
jobs de mídia, biblioteca ou outras frentes que compartilham o mesmo State
Store. Jobs interrompidos sem operação devem terminar cancelados e permitir um
retry auditável; jobs ainda queued podem receber um novo worker sem duplicação.
