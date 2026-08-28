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
