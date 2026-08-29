# Compressão negociada no transporte do core — 2026-08-28

Item: `SZ-LIBRARY-CANONICAL` (etapa "paginação do workspace" — resolve o
bloqueio de produto do `emulation workspace`). Branch `codex/library-full-scan`,
sobre `f7406f2`. Arquivos de transporte: `service/client.py`, `service/core.py`
(escopo agregado por `SZ-AGG-SERVICE-API`; sobreposição com
WS-2026-08-EMULATION-LONG-OPERATIONS registrada no workstream para arbitragem).

## Defeito reproduzido e corrigido, contra o estado REAL

Estado real copiado para scratch (`/var/tmp/sz-proof-home`, ~5 MB: `state.db`,
JSONs e config — **sem quarentena/backups de 1,2 GB; o host não foi mutado**;
`XDG_STATE_HOME`/`XDG_CONFIG_HOME` apontados para a cópia). Daemon real da
árvore (`CoreServer` + dispatch real) em socket de scratch (0700), cliente real
(`client.invoke`):

| Caminho | Resultado |
|---|---|
| **Sem compressão (cliente antigo)** | frame de **1.048.578 bytes > 1 MiB** — a falha de 2026-08-27 reproduzida byte a byte: o comando está morto no acervo real |
| **Com `acceptGzip` (cliente novo)** | `invoke` → `ok=True, status=ready`, 36 plataformas, 80 jogos, **3,9 s** |
| **Frame na rede, comprimido** | **99.620 bytes ≤ 1 MiB** (`gzip+base64`, `decodedSize=1.388.211`) — razão ~14× |

Projeção honesta: com o rescan da fonte completa (375 jogos), o payload não
comprimido cresce para ~2,5–3 MB; à razão medida o frame continua com folga
sob 1 MiB. Quando exceder o teto lógico de 8 MiB, o servidor recusa com causa
(fecha fechado) em vez de enviar algo que o cliente recusaria.

## O desenho

- **Campo de extensão no request** (`acceptGzip: true`): membro extra fora do
  `params` — servidor antigo ignora, cliente antigo nunca envia. Compatível
  nos dois sentidos, sem handshake novo.
- **Servidor** (`_encode_response`): comprime a resposta inteira só quando
  negociado, só sucesso, só acima de 256 KiB; acima de 8 MiB lógicos recusa
  com `-32003` e causa. Frame segue limitado ao cap por ser o próprio wire.
- **Cliente** (`_unwrap_result`): desembrulha transparentemente; valida
  `decodedSize` contra o descomprimido e aplica teto lógico de 16 MiB
  (defesa contra truncamento/payload malicioso). Chamadores não mudam.
- **Nenhuma forma de documento muda**: a central in-process, o QML e o
  contrato `emulation.workspace` permanecem idênticos — por isso a projeção
  enxuta foi descartada (enxugar linhas exigiria tocar `Emulation.qml`/
  `ControlsProfileCard.qml`, reservados pela WS-2026-08-V2-HARMONIZED).

## Provas automatizadas

`tests/unit/test_service_transport_compression.py` (9 testes): compressão só
quando negociada e grande; erro e resposta pequena ficam planos; round-trip
`_encode_response` → `_unwrap_result` devolve o original com frame sob o cap;
recusa de payload malformado, de `decodedSize` divergente e de descomprimido
acima do teto; recusa lógica do servidor com erro honesto; leitura do campo de
extensão. Serviço existente (`test_service_core.py`, `test_envelope.py`)
61 passed — o campo extra no request não quebra nenhum contrato testado.

## O que ainda é verdade e não muda aqui

- O read model continua gordo (`controlsProfile` de 3,7 KB por linha,
  `editorialPlatforms` duplicando jogos, 35 seções vazias de ~5,5 KB) —
  enxugar é melhoria de desempenho da central, não bloqueio de transporte.
- `E-API-RESPONSE-TOO-LARGE` segue existindo para os casos legítimos
  (gerações mistas até atualização completa; teto lógico). `manualAction` e
  `cause` atualizadas para a verdade nova.

## Rescan real pós-compressão (mesma sessão) — e correção da minha medição

Com a fonte sem amostragem em `main`, rodei o rescan do acervo real
(`scan_library()` pela árvore, 1,3 s; caches de leitura reescritos — dado
derivado, o produto é esse o trabalho; baseline dos 3 arquivos copiado para
scratch). Resultado **corrigido em relação à minha medição anterior**:

- O inventário canônico seleciona 375 "jogos únicos", mas **178 deles são
  arquivos de update/DLC/não-reconhecidos do diretório `switch/`** que o
  inventário por diretório não distingue. A dedup por caminho com o scanner
  do Switch (a autoridade em conteúdo switch) os elimina: 375 − 178 + 15
  bases reais do switch = **212 jogos verdadeiros** no read model
  (197 multi-plataforma + 15 switch). O critério "update/DLC do Switch não
  vira jogo" está cumprido no read model; o número honesto da biblioteca é
  **212, não 375** — a alegação anterior de "375/375 na fonte" minha contava
  auxiliares como jogos.
- Superfície por plataforma (`editorialPlatforms`) distribui os 212
  corretamente: master-system 51, playstation 49, nes-famicom 33,
  nintendo-handheld 30, nintendo-3ds 19, switch 15, playstation-2 6,
  dreamcast 5, wii-u 2, playstation-3 1, nintendo-console 1.
- Workspace inteiro: 3.251.981 bytes brutos → **140.113 bytes comprimidos**
  (≤ 1 MiB: o transporte carrega o estado atual num frame).
- Seção switch do workspace técnico segue como visão legada (todos os jogos
  sob a plataforma switch) — a migração dela é a etapa de consumidores, com
  QML reservado pela WS-2026-08-V2-HARMONIZED.
