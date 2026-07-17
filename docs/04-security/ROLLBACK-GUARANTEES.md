# ROLLBACK-GUARANTEES — garantias formais de rollback

## Definição

Rollback da operação O = levar os recursos tocados por O de volta ao estado registrado no backup/journal de O, **com verificação**.

## Garantias oferecidas (e seus limites)

| Classe de operação | Garantia | Limite documentado |
|---|---|---|
| Escrita de config | G-FULL: byte-idêntico via backup+hash | — |
| Instalação/atualização de componente | G-FULL para arquivos geridos; G-DEPLOYMENT para Flatpak (remote+commit anterior pinado) e G-STATE para outros pacotes | Flatpak preserva app data e pode deixar runtimes órfãos para GC; pacote nativo pode ter scripts pós-install não reversíveis — riscos no plano |
| Organização/conversão de biblioteca | G-FULL: original mantido até commit | após commit + GC do backup, reverter exige re-conversão |
| Import de dumps | G-FULL: import é cópia; fonte intocada | — |
| Saves | G-TIMELINE: qualquer versão retida é restaurável | granularidade = pontos de checkpoint/flush |
| Ações do helper privilegiado | G-STATE: valor anterior registrado e reaplicável (TDP, sysctl, unit); TDP persiste journal root antes de `slowPPT`/`fastPPT` | estado de hardware volátil (clock) se perde em reboot — por design; transporte mutável permanece gated até VM |
| Migração SSD↔microSD | G-FULL até commit (copy-verify-switch-delete) | — |

## Invariantes (testadas em ROLLBACK-TESTS)

1. **RB-1:** rollback nunca precisa de rede.
2. **RB-2:** rollback nunca precisa de mais espaço do que o liberado pela própria reversão + margem constante (backups já existem localmente).
3. **RB-3:** rollback é idempotente: rodar 2× = mesmo resultado.
4. **RB-4:** rollback verificado: compara hashes com o manifesto do backup; divergência ⇒ `rollback-failed` explícito (nunca "sucesso" otimista). Supera o `pz_rollback` do PhaseZero, que restaura com `cp` e não verifica (common.sh:545).
5. **RB-5:** falha parcial preserva o manifesto: entradas revertidas marcadas, pendentes mantidas (o PhaseZero atual apaga o manifesto inteiro — common.sh:554 — anti-padrão corrigido).
6. **RB-6:** dados do usuário criados **depois** da operação (saves novos, por ex.) nunca são destruídos por rollback — rollback de componente não toca stores de dados de usuário.
7. **RB-7:** todo plano informa, antes do apply, a garantia de rollback da operação (G-FULL/G-STATE/G-TIMELINE) e o que NÃO é reversível.

## Retenção e GC de backups

Política padrão: manter backups das últimas N operações por recurso + tudo dos últimos D dias (config), com teto de disco; GC nunca remove o backup da última operação de cada recurso; GC é ele próprio uma operação com plan/preview (corrige "backups infinitos" do `pz_write_managed_file`).
