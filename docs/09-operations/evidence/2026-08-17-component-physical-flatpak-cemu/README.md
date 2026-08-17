# Cemu Flatpak — bloqueio físico externo

Data: 2026-08-17  
Release instalada: `0.1.0a46-fe360b3731d5`

## Resultado observado

O baseline do host real encontrou Cemu ausente, instalável e roteado pelo
executor Flatpak, com destino pinado
`cbadbabac58e89f72a9dbd18b93ed19dbadf678f44412ffc8edb98e630ddec1f`.
Não havia deployment `info.cemu.Cemu` no inventário Flatpak do usuário.

O planejamento `component plan --id cemu --action install` foi
metadata-only. Duas autorizações novas, executadas uma única vez cada pelo
fluxo governado, terminaram em `E-SUPPLY-REMOTE-FAILED`: a resolução de
`dl.flathub.org` falhou ao buscar o índice do repositório. Cada plano foi
terminalizado como `aborted`; uma tentativa de reutilizar a primeira
autorização foi corretamente recusada como plano obsoleto.

Depois da segunda falha independente, a execução foi interrompida conforme o
critério de produtividade. Cemu permaneceu `missing`, não criou dados do
aplicativo nem deployment Flatpak e não há captura visual a registrar: o
componente não chegou a uma superfície utilizável. Este é um bloqueio de rede
externo, não uma correção de código concluída.

## Próxima ação

Retomar o ciclo físico do Cemu somente quando a resolução do repositório estiver
disponível. Não repetir a mesma tentativa enquanto essa condição externa não
mudar.
