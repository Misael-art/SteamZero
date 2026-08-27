# Matriz física dos 33 componentes (2026-08-27)

Item: `SZ-COMPONENT-LIFECYCLE`
Release ativa: **`2.0.0rc1-3b296a949316`**, daemon na mesma geração
Host: Valve Jupiter (Steam Deck LCD)

Medido com `steamzero component list` — read-only, sem nenhuma mutação.

## Resultado

```
total ......... 33
estados ....... missing 22 · installed 9 · degraded 2
executores .... libretro 17 · flatpak 10 · engine 6
degradados sem detail ... NENHUM
```

## Os dois degradados, com causa registrada

```
dolphin    flatpak  commit instalado 1b150924d321 difere da fonte fixada 377c3e63506e
retroarch  flatpak  commit instalado 1f766799d9ff difere da fonte fixada d8644a97df3d
```

Ambos por divergência de commit Flatpak, não por falha. A exigência da §8 —
degradar com causa registrada — está cumprida em 2 de 2.

## Os 9 instalados

`cemu`, `citron`, `duckstation`, `eden`, `flycast`, `melonds`, `pcsx2`, `rpcs3`,
`ryubing`. Todos com `detail: null`, que é o correto para estado saudável.

## O achado estrutural: os cores libretro

**Os 17 cores libretro estão todos `missing`.** Nenhum foi instalado alguma vez
neste host.

Isso é 52% da matriz. O número "33 componentes" esconde que a maioria é de uma
categoria inteira sem nenhuma instalação física — e portanto sem nenhuma prova
de que o ciclo install/verify/rollback funcione para o executor `libretro`.

O que existe hoje de prova física por executor:

| executor | total | instalados | provado fisicamente |
|---|---|---|---|
| `flatpak` | 10 | 6 | sim — inclusive `melonds` pelo fluxo governado |
| `engine` | 6 | 4 | sim — AppImage |
| `libretro` | 17 | **0** | **não** |

A conformidade local cobre os 33 (357 passed em teste), mas cobertura de teste
não é instalação. Para o executor `libretro`, matriz local verde e matriz física
vazia coexistem.

## O que esta página não prova

Nada sobre progresso por bytes nem cancelamento cooperativo na aquisição — os
dois seguem sem instrumentação. E nada sobre o ciclo `libretro`, pelo motivo
acima: sem um core instalado, não há o que verificar ou reverter.

Instalar um core exigiria `component apply`, que é mutação: depende de
autorização explícita do operador e, nesta sessão, foi bloqueado pelo
classificador do harness.

## Estado do host

Inalterado. `component list` é read-only.
