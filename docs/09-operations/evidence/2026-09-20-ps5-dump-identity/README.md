# PS5 — identidade dos dumps do operador

Esta evidência registra somente a inspeção de identidade dos dois dumps PS5
disponíveis no host. Nenhum arquivo da origem foi alterado.

- `PPSA02929` foi extraído para uma árvore temporária a partir do RAR e expôs
  `eboot.bin` + `sce_sys/param.json`.
- `PPSA02801` foi montado com `guestmount --ro` a partir da imagem exFAT e
  expôs `eboot.bin` + `sce_sys/param.json`.
- O leitor reconheceu ambos por `titleId` e retornou o diagnóstico
  `ps5-param-json`.

Esta é prova de ingestão/identidade, não prova de lançamento SharpEmu. A
validação física de execução ainda exige uma release instalada que contenha o
adapter, SharpEmu disponível e captura PNG do jogo real.
