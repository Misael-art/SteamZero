# EMULATOR-DOSSIER — Nintendo Switch

**Slug:** `switch` · **Onda:** 0 · **Status:** revisão · **Estudo:** 2026-07-24

> A Onda 0 foi especificada como "revisar dossiê existente". **Não existia
> dossiê** (D2 do `STUDY-LEDGER.md`). Este documento **consolida** o material já
> commitado — `EMULATOR-PORTING-DIRECTIVE.md`, `ADR-0021`,
> `SWITCH-MEDIA-PROVIDER-PLAN.md` e os três manifestos de emulador — no formato
> normativo do §5, e marca o que precisa de reverificação externa.

> ⚠️ **Limite desta sessão:** os fatos abaixo vêm do repositório, onde estão
> commitados com versão e SHA-256. O **estado upstream atual** dos três projetos
> não foi reverificado (D4 do ledger: `WebSearch`/`WebFetch` indisponíveis;
> `git.eden-emu.dev` respondeu 403 ao acesso automatizado). Tudo que dependa de
> "o projeto ainda está vivo hoje" está marcado `[validar no spike]`.

---

## 1. Recomendação: emulador primário / alternativa

Três adapters já estão commitados em `src/steamzero/adapters/manifests/`. O
escopo alvo da porting-directive nomeia exatamente estes: "Emuladores de Switch
alvo: Eden, Citron, Ryujinx-sucessores".

| Emulador | Versão pinada | Licença | Fonte pinada | Canal |
|---|---|---|---|---|
| **Eden** | `0.2.1-steamdeck` | GPL-3.0-or-later | AppImage `stable.eden-emu.dev`, SHA-256 `5cc5b358…` | estável |
| **Ryubing** | `1.3.3` | MIT | AppImage `git.ryujinx.app`, SHA-256 `b4511f46…` | estável |
| **Citron** | `2026.04.27-0237a9b88` | *(não declarada no manifesto)* | AppImage GitHub `citron-neo/emulator`, SHA-256 `bf62002f…` | **nightly** |

**Primário: Eden.** A build pinada é a variante **`steamdeck-clang-pgo`** — o
upstream publica um artefato otimizado especificamente para o hardware alvo, o
que é o critério de desempate deste projeto (melhor experiência no Deck).

**Alternativa: Ryubing.** Licença MIT e `configFormat: json` — JSON é
estruturalmente mais seguro de fazer parser com diff do que INI, o que reduz o
risco da invariante §2.2. Vale como segundo caminho para jogos onde o Eden
falhar.

**Citron: manter, com ressalva registrada.** Está pinado numa **nightly**
(`2026.04.27`), e a regra 2 do `ADAPTER-MODEL.md` diz que `versionPolicy:
latest`/nightly só é admissível em canal dev com checksum no lockfile. O
manifesto pina SHA-256, o que satisfaz a parte do checksum. **Pendência:** o
manifesto do Citron não declara `license` — os outros dois declaram.
`[validar no spike]` a licença e se existe canal estável.

## 2. Adapter: manifesto, canal, modelo de config + parser

Os três manifestos declaram o mesmo enum fechado de dez capacidades
(`detect,status,install,update,configure,verify,repair,uninstall,backup,restore`)
— o enum que a `ADR-0021` decidiu **manter fechado**.

- `configFormat`: `ini` (Eden, Citron) e `json` (Ryubing).
- `verify.smokeTest`: `["--appimage-version"]` nos três.
- `requiresKeys: {platform: switch, keyset: prod}` e `requiresFirmware` nos três.

**Consequência arquitetural já decidida (ADR-0021):** importar keys/firmware,
converter NSZ, casar DAT, deduplicar conteúdo e migrar saves **não** são
capacidades de emulador. Foram para domínios dedicados. Qualquer WI futuro que
queira `import-keys` no adapter está reabrindo uma decisão aceita.

## 3. BIOS / firmware / keys — **o ponto mais sensível de todos os sistemas**

Regras já vigentes, não negociáveis (regra 5 das invioláveis da porting-directive):

- Keys e firmware são **conteúdo do usuário**. O produto **valida o que o usuário
  já tem; nunca obtém, sugere ou baixa**.
- Nomes de keys e hashes completos **nunca** vão para logs, state ou argv em
  claro (SR-14) — só hash truncado.
- Store: `domain/bios.py`, já commitado, keys-aware.
- `local-owned-dump-only` (invariante §2.5).

Este dossiê **não** documenta procedimento de obtenção de keys, e nenhum dossiê
futuro deve.

## 4. Config-per-game (P1) — **aplica**

`[validar no spike]` quais chaves de configuração por jogo cada emulador expõe em
arquivo e se há base de compatibilidade consumível como dado (com licença
compatível). Para NES isso está resolvido pela base interna do emulador
(ver `nes.md` §4); no Switch o equivalente ainda não foi levantado.

## 5. Inputs exóticos (P2) — **aplica parcialmente**

Candidatos óbvios do console: giroscópio nativo (o Switch tem, o Deck tem),
rumble HD, IR da Joy-Con direita, touch da tela. `[validar no spike]` o que cada
emulador expõe. **Não afirmo mapeamento sem medir** — este é o sistema onde a
tentação de prometer é maior e o custo de errar também.

## 6. Multiplayer (P3) — **aplica, com limitação honesta**

O Switch tem **LDN** (local wireless) e online. Nenhum dos três manifestos
declara suporte, e a diretiva `COOP-ONLINE` referenciada pelo §1 do diretivo de
estudo **não existe no repositório** (D3 do ledger).

**Limitação honesta:** online oficial exige serviço da Nintendo e conteúdo
protegido — fora de escopo pelo §9.3 do diretivo de estudo. LDN entre duas
instâncias locais é o único caminho que este projeto pode perseguir.
`[validar no spike]`.

## 7. Periféricos / expansões (P4/P5)

`[validar no spike]`. Sem levantamento nesta sessão.

## 8. Mods / patches (P6) — **aplica, e já existe código**

O repositório tem `src/steamzero/adapters/mods/` e `src/steamzero/adapters/cheats/`
commitados, com catálogo de erros próprio (`E-MOD-*`, `E-CHEAT-*` em
`core/errors.py`), incluindo `E-MOD-BUILD-ID-MISSING` — ou seja, o produto já
modela que mod de Switch é casado por build ID do jogo. Este dossiê **consome**
esse trabalho; não o reabre.

## 9. "Como era" selecionável (P7) — **não aplica**

O Switch é a geração corrente do escopo; não há "artifact colors", slowdown
original ou chip de áudio a restaurar. Os ganchos WI-R (escala inteira, CRT,
timing) foram desenhados para o retro. **Marcado explicitamente como não
aplicável** para não deixar seção vazia sem justificativa (§7 do checklist).

## 10. Robustez

- **Instalação/atualização/rollback:** já resolvido pelo núcleo transacional; os
  três adapters declaram as dez capacidades.
- **Config e ownership:** dois dos três usam INI. Parser estrutural com diff é
  obrigatório; comportamento de FM-22 se o emulador reescrever por fora.
- **Saves:** domínio Saves central; o adapter não faz backup de saves.
- **Performance no Deck:** **não medida.** O Switch é o sistema mais caro da fila
  e o mais sujeito a promessa vazia. Nenhum número neste dossiê.
- **FM propostos:** nenhum novo. Os modos de falha do Switch já estão cobertos
  pelos códigos `E-MOD-*`/`E-CHEAT-*`/`E-CONTENT-*` e por FM-22. Propor FM
  aditivo aqui sem medição seria ruído.

## 11. Momento mágico + critério de aceite

> **O usuário importa suas próprias keys e firmware uma vez; a partir daí
> qualquer jogo da biblioteca abre pelo Game Mode sem que ele volte a pensar em
> keys.**

Critério de aceite: importar keys e firmware pela central; instalar Eden;
lançar um título; e — o teste que importa — **desinstalar e reverter**, com o
store de keys intacto e nenhum hash completo em log algum.

## 12. Riscos / licenças / supply chain

| Risco | Severidade | Nota |
|---|---|---|
| Vazamento de nome/hash de key em log ou argv | **alta** | SR-14 já vigente; qualquer WI toca isso com teste dedicado |
| Citron pinado em nightly sem licença declarada | média | Bloquear promoção do Citron a primário até resolver |
| Projetos de emulação de Switch são historicamente voláteis | **alta** | `versionPolicy: pinned` isola o produto; ter três adapters é a mitigação estrutural |
| Estado upstream não reverificado nesta sessão | média | D4 do ledger; primeira tarefa do WI |

**Questões para o operador:**

1. O Citron deve continuar como terceiro adapter pinado em nightly, ou sai até
   ter canal estável e licença declarada?
2. LDN vale um estudo próprio, dado que `COOP-ONLINE` não existe?

## 13. Fontes

**Internas (commitadas, verificáveis no repo):**
`src/steamzero/adapters/manifests/{eden,ryubing,citron}.adapter.json` ·
`docs/12-roadmap/EMULATOR-PORTING-DIRECTIVE.md` ·
`docs/adr/0021-dominios-dedicados-keys-firmware-conversao-dat.md` ·
`docs/03-architecture/ADAPTER-MODEL.md` · `src/steamzero/core/errors.py`
(catálogo `E-MOD-*`/`E-CHEAT-*`) · `src/steamzero/adapters/{mods,cheats}/`.

**Externas:** nenhuma consultada nesta sessão. `stable.eden-emu.dev`,
`git.ryujinx.app` e `github.com/citron-neo/emulator` constam nos manifestos mas
**não foram reverificados** — ver D4 do ledger.

## 14. WI proposto para a PORTING-DIRECTIVE

**WI-S0 — Reverificação de proveniência dos adapters de Switch**

- **Objetivo:** trazer os três manifestos ao estado corrente e fechar as lacunas
  de licença/canal, antes de qualquer novo trabalho de Switch.
- **Entregáveis:** estado upstream dos três projetos com fonte e data; licença do
  Citron declarada ou adapter removido; versões e SHA-256 reconferidos; decisão
  registrada sobre nightly do Citron.
- **Gates:** os quatro de sempre; `component-lock.json` coerente.
- **Dependências:** nenhuma. É pré-requisito dos demais WIs de Switch.

Os WI-0 a WI-9 da porting-directive **já cobrem** keys/firmware, conversão NSZ,
No-Intro, compartilhamento, controles e LSFG. Este dossiê não os duplica.
