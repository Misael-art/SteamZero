# Evidência física — `detail` em componente degradado (2026-08-25)

Item: `SZ-EMULATION-LONG-OPERATIONS`
Release validada: **`2.0.0rc1-92d91d631b80`** (`--source-commit 92d91d631b80d47ea080be2e8dc7da3fa4ff39f4`, `refs/heads/main`)
Release anterior, preservada para rollback: `2.0.0rc1-2a1b0fb90105`
Host: Valve Jupiter (Steam Deck LCD)

## O que esta evidência prova

O commit `2a4e6ae` fez `flatpak.status` nomear os dois commits quando o commit
implantado diverge da fonte fixada. Antes, o executor Flatpak marcava `degraded`
com `detail: None`, enquanto o executor engine já registrava a causa — o
requisito da seção 8 do AGENTS.md ("falha degrada, nunca trava", com causa
registrada) era cumprido por um executor e não pelo outro.

A prova local já existia no item. O que faltava era a prova **física**: o item
registrava o defeito observado no host com a `2a1b0fb90105` instalada, e a
correção só valia como entregue depois de observada na release instalada.

## Natureza dos arquivos

Os três PNGs são **renderizações fiéis de stdout real capturado** da release
instalada, não capturas de tela e não transcrições reescritas. Cada quadro traz o
comando exato acima da saída, então qualquer pessoa pode reexecutar e comparar.

Não há captura de GUI porque o campo `detail` de componente **não é renderizado
em nenhuma superfície QML** — a correção é de backend e sua única superfície
observável é o CLI. Uma janela do launcher apareceria como evidência sem mostrar
a entrega.

| Arquivo | Conteúdo |
|---|---|
| `01-baseline.png` | Release ativa, versão efetiva, binários no PATH, `doctor`, units |
| `02-entrega-funcional.png` | `detail` preenchido em `dolphin` e `retroarch` + matriz dos 33 |
| `03-recuperacao.png` | Erro controlado (`E-API-SCHEMA`), recuperação e rollback disponível |

## Resultado medido

```
total ............... 33
estados ............. {'missing': 23, 'installed': 8, 'degraded': 2}
degradados .......... 2
  dolphin      executor=flatpak  detail='commit instalado 1b150924d321 difere da fonte fixada 377c3e63506e'
  retroarch    executor=flatpak  detail='commit instalado 1f766799d9ff difere da fonte fixada d8644a97df3d'
degradados SEM detail NENHUM
```

O `detail` do `dolphin` no host é textualmente igual ao que o commit `2a4e6ae`
afirmou ter verificado na árvore corrigida. A afirmação do commit e o
comportamento da release instalada coincidem.

## Leitura honesta dos dois `warn` do doctor

`doctor` saiu com **`degraded` e exit code 0**. Isso é o contrato: só `failed`
sai com 1. Os dois `warn` são anteriores a esta entrega e não foram introduzidos
por ela:

- `backup.orphan: 1 backup(s) sem operação no banco` — resíduo de operação
  anterior, fora do escopo deste item.
- `boot.direct: unknown: Sem permissão para inspecionar a configuração de boot.`
  — o `unknown` por falta de permissão é exatamente o estado degradado previsto
  pela seção 8, não uma falha silenciosa.

`service.generation` passou com `daemon na release ativada
2.0.0rc1-92d91d631b80`, o que prova que o daemon reiniciou na geração nova —
condição sem a qual o `component status` teria respondido pelo código antigo e a
evidência inteira seria inválida.

## Reexecução

```bash
steamzero --version
steamzero doctor
steamzero component status --id dolphin
steamzero component status --id retroarch
steamzero component list
```
