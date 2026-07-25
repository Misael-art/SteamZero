# EMULATOR-DOSSIER — Nintendo Switch

**Slug:** `switch` · **Onda:** 0 · **Status:** revisão · **Estudo:** 2026-07-24

> A Onda 0 foi especificada como "revisar dossiê existente". **Não existia
> dossiê** (D2 do `STUDY-LEDGER.md`). Este documento **consolida** o material já
> commitado — `EMULATOR-PORTING-DIRECTIVE.md`, `ADR-0021`,
> `SWITCH-MEDIA-PROVIDER-PLAN.md` e os três manifestos de emulador — no formato
> normativo do §5, e marca o que precisa de reverificação externa.

> ✅ **Reverificado em 2026-07-25** por coleta externa. Os três projetos estão
> ativos, as licenças estão resolvidas — e apareceram dois problemas de
> proveniência que não eram visíveis antes (§1).

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

**Citron: fica** (decisão do operador, 2026-07-24). A pendência de licença está
**resolvida** e apareceu uma oportunidade.

### Reverificação de 2026-07-25

| Emulador | Estado upstream | Licença | Consultado |
|---|---|---|---|
| Eden | estável **v0.2.1** (2026-06-01); último commit **2026-07-25** — ativo. Publica AppImages dedicadas "Steam Deck (Zen 2)", standard e PGO | **GPLv3** (`LICENSE.txt`) | 2026-07-25 |
| Ryubing | estável **1.3.3** (2025-10-11); último commit **2026-07-17** — ativo | **MIT** (`LICENSE.txt`) | 2026-07-25 |
| Citron | último release **2026-04-27**; último push **2026-07-22** — ativo, mas ~3 meses sem release | **GPL-3.0** (campo de licença do repositório) | 2026-07-25 |

**A licença do Citron é GPL-3.0.** O manifesto não a declara — é lacuna do nosso
manifesto, não do projeto. Correção trivial no WI-S0.

### ⚠️ Dois problemas de proveniência descobertos

**1. Existe canal estável do Citron, e nós pinamos a nightly.** A release de
2026-04-17 publicou assets `citron_stable-*` (AppImage x86_64, x86_64_v3,
aarch64). A de 2026-04-27, que é a que pinamos, publicou **só** `citron_nightly-*`.
Ou seja: dá para sair da nightly sem perder o adapter — basta repinar na
2026-04-17. Isso resolve a tensão com a regra 2 do `ADAPTER-MODEL.md` que este
dossiê havia registrado. *(Não há documento formal da política de canal; a
distinção vem da nomenclatura dos assets — `[hipótese de processo, fato de
nomenclatura]`.)*

**2. Os assets do Ryubing 1.3.3 foram recriados depois da publicação.** A release
é de 2025-10-11, mas os artefatos têm timestamp **2026-03-30**, da migração
GitLab→Forgejo. **Um SHA-256 pinado antes de março/2026 pode não bater com o
download atual.** O nosso manifesto pina `b4511f46…`; precisa ser reconferido
contra o arquivo servido hoje — se divergir, a instalação falha no checksum, que
é o comportamento correto, mas por um motivo que ninguém entenderia sem esta nota.

**3. Nenhum dos três publica SHA-256.** Nem Eden (testados `SHA256SUMS`,
`checksums.txt` e variantes — todos 404), nem Ryubing (a 1.3.2 tinha `.zsync`,
que sumiu na 1.3.3), nem Citron. Os hashes dos nossos manifestos foram
necessariamente calculados no primeiro download. Isso é aceitável, mas deve ser
**declarado como política**, não ficar implícito — vale para o MesenCE também
(ver `nes.md` §2).

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

**Externas (coleta de 2026-07-25):**

| URL | Uso |
|---|---|
| `https://git.eden-emu.dev/api/v1/repos/eden-emu/eden/releases` e `/commits` | v0.2.1, builds Steam Deck, atividade |
| `https://git.eden-emu.dev/eden-emu/eden/src/branch/master/LICENSE.txt` | GPLv3 |
| `https://git.ryujinx.app/projects/Ryubing/releases/tag/1.3.3` | versão, assets recriados |
| `https://git.ryujinx.app/projects/Ryubing/raw/branch/master/LICENSE.txt` | MIT |
| `https://api.github.com/repos/citron-neo/emulator` | licença GPL-3.0 |
| `https://github.com/citron-neo/emulator/releases/tag/2026-04-17` | existência de assets `citron_stable-*` |

Nota de método: `git.ryujinx.app` tem anti-bot (Anubis PoW) e exigiu navegador
real; `git.eden-emu.dev` respondeu bem à API REST — o 403 anterior era da UI
HTML, não da API.

## 14. WI proposto para a PORTING-DIRECTIVE

**WI-S0 — Reverificação de proveniência dos adapters de Switch**

- **Objetivo:** corrigir os manifestos com o que a coleta de 2026-07-25 apurou.
- **Entregáveis (agora concretos, não mais exploratórios):**
  1. declarar `"license": "GPL-3.0"` no manifesto do Citron;
  2. **repinar o Citron na release estável de 2026-04-17** (`citron_stable-*`),
     saindo da nightly — resolve a tensão com a regra 2 do `ADAPTER-MODEL.md`;
  3. **reconferir o SHA-256 do Ryubing 1.3.3** contra o arquivo servido hoje: os
     assets foram recriados em 2026-03-30 e o hash pinado pode estar obsoleto;
  4. confirmar que o Eden segue na `v0.2.1` PGO para Steam Deck;
  5. registrar em `ADAPTER-MODEL.md` a **política de hash calculado localmente**,
     já que nenhum dos quatro emuladores estudados publica SHA-256.
- **Gates:** os quatro de sempre; `component-lock.json` coerente; instalação de
  cada adapter exercitada com o hash novo.
- **Dependências:** nenhuma. É pré-requisito dos demais WIs de Switch.

Os WI-0 a WI-9 da porting-directive **já cobrem** keys/firmware, conversão NSZ,
No-Intro, compartilhamento, controles e LSFG. Este dossiê não os duplica.
