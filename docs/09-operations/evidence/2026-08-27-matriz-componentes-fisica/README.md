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

---

## Primeira instalação física de um core libretro (2026-08-27)

Autorizada explicitamente pelo operador. `libretro-snes9x`, pelo fluxo governado
`component plan` → `component apply`, plano `01M11XYJ33WCB1G266MK69Z63F` com
`rollbackGuarantee: G-FULL`.

Esta é a **primeira** instalação do executor `libretro` neste host. Antes dela a
tabela acima registrava `libretro 17 / 0 instalados / não provado`.

### Antes e depois

| | antes | depois |
|---|---|---|
| `state` | `missing` | **`installed`** |
| `version` | `null` | `1.22.2` |
| `origin` | `null` | `archive` |
| `verified` | — | **`true`** |
| árvore de cores | inexistente | criada |

### O digest que já causou defeito neste repo

O plano declarou duas âncoras distintas:

```
archiveSha256  4b7ed8dc97d4bf035fce182c64b5658c7662e2e9e5d42129538afbd4b6096307
coreSha256     f7eb400380a18e94b996acfae5a22fa4261c8ff90fa24c213336548925036442
```

O `coreSha256` é o **segundo** digest — o do `.so` extraído, não o do pacote — e
já foi origem de defeito de produto: `_owned_target` comparava com o digest
errado e recusava todo update com `E-CONTENT-INCOMPLETE`.

Conferido no artefato real:

```
$ sha256sum ~/.var/app/org.libretro.RetroArch/config/retroarch/cores/snes9x_libretro.so
f7eb400380a18e94b996acfae5a22fa4261c8ff90fa24c213336548925036442
                                                    2 161 408 bytes
```

**Idêntico ao declarado.** O que foi planejado é o que está no disco.

### Ownership

```json
{"adapterId":"libretro-snes9x","archiveSha256":"4b7ed8dc…","coreId":"snes9x",
 "coreSha256":"f7eb4003…","manifestHash":"5361ac9c…","schemaVersion":1,
 "version":"1.22.2"}
```

Marcador em `cores/.steamzero-managed/libretro-snes9x.json`, com as três âncoras
registradas — o que permite distinguir core nosso de core de terceiro numa
remoção ou update futuro, exigência da §5.

### Onde o core foi parar, e por que isso importa

`~/.var/app/org.libretro.RetroArch/config/retroarch/cores/` — o diretório de
configuração do Flatpak, **gravável a partir do host**.

Contraste que vale registrar: no caso do autoconfig, o
`joypad_autoconfig_dir` declarado apontava para `/app/share/…`, interno ao
sandbox e inalcançável. Para cores, o caminho é alcançável. As duas
integrações com o mesmo Flatpak têm superfícies de escrita diferentes, e supor
uma pela outra levaria a erro.

### O que continua não provado

`rollback` do core **não foi executado** — a operação está disponível no journal
e não foi acionada, porque reverter uma instalação recém-provada destruiria a
evidência sem pedido do operador. `update` de core também não foi exercido.

Progresso por bytes e cancelamento cooperativo seguem sem instrumentação.

Os outros **16 cores libretro continuam `missing`**. Um core instalado prova que
o executor funciona; não prova os sete emuladores que dependem de cores ainda
ausentes.
