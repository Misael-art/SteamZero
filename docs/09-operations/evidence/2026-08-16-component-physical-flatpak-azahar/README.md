# Componente físico Flatpak: Azahar

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base do incremento: `bacb5b8`

## Escopo

Executar no host real, no escopo Flatpak do usuário, o ciclo individual de
Azahar: baseline, plan metadata-only, install, verify, segunda instalação
idempotente, repair, falha controlada, rollback e uninstall preservando dados.

O código executado vem do commit limpo da branch pelo `PYTHONPATH`. A plataforma
SteamZero instalada não será substituída: o fluxo governado exige artifact de
CI remoto, enquanto o pedido adia push até a certificação final.

## Hipótese inicial

O baseline informado registra Azahar ausente e três tentativas anteriores
falhando na resolução transacional, apesar de a consulta direta do commit
pinado funcionar. A primeira etapa deve reproduzir ou refutar essa divergência
sem deixar plano ou operação pendente.

## Estado

Reservado. Baseline físico ainda não capturado.
