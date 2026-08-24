# Baseline da harmonização v2

Data: 2026-08-23  
Branch: `codex/v2-harmonized-functional-release`  
Base: `c2a1ff1abc98fbffd04175c81010009872476893` (tip de `origin/main`)

## Host no momento do baseline

- Release ativa: `0.1.0a46-5b41f2edbf78` (commit `5b41f2edbf78fa2578f18673bf5f5f5a6a822f11`,
  tip de `codex/physical-functional-closure`, instalada pelo fluxo governado
  `release_host.py update` com run CI verde `32632912949`).
- Rollback disponível: `0.1.0a46-bd598c516bce`.
- Serviço e socket ativos; daemon convergido na release ativada.
- `doctor`: degraded apenas por `backup.orphan` (1 backup sem operação, já
  conhecido e em investigação sem remoção) e `boot.direct unknown` (leitura de
  boot exige privilégio — read-only).

## Componentes (33 catalogados)

- 8 instalados: cemu, citron, duckstation, eden, flycast, pcsx2, rpcs3, ryubing.
- 2 degradados: dolphin, retroarch.
- 23 ausentes.

## Tema

- `theme status` retorna `ok` com `activeId=org.steamzero.asset-recipes-demo`
  e `resolved=null` — falso verde ao vivo, tema ausente do catálogo sem
  diagnóstico nem fallback (defeito a corrigir na entrega 6.6).

## Biblioteca / mídia

- Configuração aponta apenas raízes Switch/Firmware; banco canônico sem jogos;
  cache paralelo com 15 jogos Switch; acervo físico ~198 diretórios.

## Frontends

- ES-DE: backend parcial sem jornada QML completa.
- RetroFE: importação/lançamento incompletos.
- AURA Launcher: não existe na release instalada.

## Auditoria UI

- 378 controles `not-probed` registrados pela auditoria anterior.

## Prova física recém-concluída (frente anterior)

Invariante de payload executável provado no host contra `0.1.0a46-5b41f2edbf78`
(ver evidência `2026-08-22-component-executable-payload` na branch
`codex/physical-functional-closure`): detecção `degraded`, verify honesto,
recusa estruturada de launch, repair por job, launch/stop reais e dados
preservados. Esta capacidade entra na matriz de harmonização para porte à main.
