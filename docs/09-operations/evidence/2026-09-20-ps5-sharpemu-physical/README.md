# Validação física PS5 / SharpEmu

## Resultado

Em 2026-09-20, a release instalada `2.0.0rc1-3acc2104dd5a` foi usada para
lançar um dump real do operador (`PPSA02929`, Dreaming Sarah) no SharpEmu
`0.0.3-release.4`.

O resultado é uma falha controlada de compatibilidade, não uma prova de jogo
renderizado: o loader abriu `eboot.bin`, leu `sce_sys/param.json`, identificou
o Title ID `PPSA02929` e a versão `01.000.000`, mas o guest terminou com
`Access Violation` após um import HLE não encontrado. Não foi publicada uma
captura PNG de sucesso porque nenhuma cena do jogo chegou a ser renderizada.

## Evidência

- [PHYSICAL-VALIDATION.json](PHYSICAL-VALIDATION.json)
- Log bruto local da execução: `/tmp/sharpemu-ps5.log` (não é artefato de
  release; preservado somente no host para diagnóstico)

O dump original permaneceu intacto. Nenhum reboot, encerramento ou alteração da
sessão do KDE foi executado.

## Próxima ação

Manter `GAP-SHARPEMU-PHYSICAL-VALIDATION` aberto e repetir a prova somente após
uma versão do SharpEmu com o import/runtime necessário corrigido ou com outro
dump compatível. A identidade do dump e a instalação do componente estão
provadas; a compatibilidade funcional ainda não está.
