# 26 — fora de escopo: duas grandezas fora do cartão, declaradas com dono

A UX-04 varre os **cartões** do workspace (evidência 21) e as **páginas** que o
gate executa (18/19/24/25). Ao executar as quatro páginas lado a lado nesta
rodada, apareceram duas leituras de grandeza que não passam por nenhum dos dois
caminhos. Nenhuma foi corrigida aqui: `AGENTS.md` §2 não permite editar arquivo
com dono exclusivo de outra frente ativa, e o operador pediu reconciliação de
claims antes de mexer em compartilhado. Ficam medidas, com o corte que as fecha.

## F-1 — memória disponível: número binário com rótulo decimal, sem localização

**Superfície.** `src/steamzero/ui/qml/SteamGameplay.qml:1320`

```qml
text: page.hardware.memoryGb ? page.hardware.memoryGb + " GB" : "—"
```

**Produtor.** `src/steamzero/adapters/steam_gameplay.py:965-972`

```python
def _memory_gb(self) -> float | None:
    ...
    if line.startswith("MemAvailable:"):
        return round(int(line.split()[1]) / 1024 / 1024, 1)
```

**Medição neste host (2026-09-28).** `/proc/meminfo` lia
`MemAvailable: 7254368 kB` = `7 428 472 832` bytes. A função devolve
`round(7428472832 / 1024 / 1024, 1) = 6.9`. As três leituras:

| leitura | valor | o que a tela diz |
|---|---|---|
| binária real (GiB) | 6,92 GiB | — |
| decimal real (GB) | 7,43 GB | — |
| **impressa** | `6.9 GB` | número GiB rotulado GB, com ponto |

Dois erros em uma linha, e o primeiro é o que o contrato da UX-04 já proíbe para
cartões: *rótulo decimal sobre divisor binário afirma ~7 % menos que o medido*
(`docs/06-api/JSON-SCHEMAS.md`, invariante 3 — medido aqui: `-6,87 %`). O
segundo: a concatenação em QML usa a conversão JS do número, que não localiza
(medido na sonda da evidência 24: fora do `pt_BR`, `6.9` continua `6.9`), então
um usuário em pt_BR lê `6.9 GB` onde o resto do shell lê `6,9 GiB`.

**Por que não é desta frente.** O valor é pino de
`tests/unit/test_desktop_dashboard.py:724` (`== 11.2`), arquivo **exclusive** de
`WS-2026-09-RC01-READINESS-SEMANTICS`, que também tem
`src/steamzero/adapters/steam_gameplay.py` no escopo compartilhado. Trocar o
contrato do painel (`memoryGb` → `memoryBytes`) mexe num teste que outra frente
está escrevendo agora — editar WIP alheio para o meu gate ficar verde é o
atalho que a diretriz do operador proíbe.

**Fecho proposto (corte seguinte, com o dono na série).** O produtor publica
`memoryBytes` inteiro (mesma forma de `metricBytes`), a página lê pelo
`Sizes.bytes`, e o pino de `test_desktop_dashboard.py` é atualizado pela frente
que o possui. A mudança é de contrato, não de rótulo: `11.2` não é uma unidade
localizável.

## F-2 — preview do plano: bytes crus vindos do produtor

**Produtor.** `src/steamzero/adapters/emulation.py:2989-2996` monta
`plan_extra["preview"]` com

```python
f"{package_plan.estimated_output_bytes:,} bytes; exige "
f"{package_plan.required_space_bytes:,} bytes livres antes de iniciar. "
```

**Consumo.** `src/steamzero/ui/qml/Main.qml:1906` imprime
`root.emulationPlan.preview` cru, em `Text`.

O `,:` do formatador Python é fixo e não é o separador do aparelho, e o número
aparece sem andar, na mesma tela onde o cartão do volume já lê pelo formatador. É o
defeito que a UX-04 fechou em cartão, reaparecendo em prosa de **plano**, que a
varredura de cartões da evidência 21 não alcança por definição (o preview não é
um cartão do workspace; é texto de pré-visualização de ação).

**Por que não é desta frente.** `src/steamzero/adapters/emulation.py` tem dono
exclusivo medido — `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT` — e seis claims
compartilhados ativos. Além disso, o `preview` é uma string do contrato de plano
de ação: trocá-la por campos numéricos (`estimatedOutputBytes`,
`requiredSpaceBytes`) e deixar a superfície formatar é mudança de contrato do
fluxo transacional, não um re-rótulo, e tem a frente dona por frente.

**Fecho proposto.** Publicar a estimativa como inteiros no plano e compor a frase
na superfície com `Sizes.bytes`, mantendo o texto explicativo onde ele já é
política ("sem renomear, mover ou apagar a origem"). Serializado com F-1: as
duas tocam produtores de outra frente e exigem a série de integração, não um
commit paralelo.

## Medição de donos (reprodutível)

Pertencência exata por prefixo sobre `docs/status/workstreams/*.json` com
`state == "active"` (11 frentes):

| caminho | exclusive | compartilhado por |
|---|---|---|
| `tests/unit/test_desktop_dashboard.py` | `WS-2026-09-RC01-READINESS-SEMANTICS` | 1 |
| `src/steamzero/adapters/steam_gameplay.py` | — | 1 (`…READINESS-SEMANTICS`) |
| `src/steamzero/ui/qml/SteamGameplay.qml` | — | 2 (`…READINESS-SEMANTICS`, `…STORAGE-UNITS`) |
| `src/steamzero/adapters/emulation.py` | `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT` | 6 |
| `src/steamzero/ui/qml/Main.qml` | `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT` | 5 |
| `tests/integration/test_qml_handheld_offscreen.py` | `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT` | 3 |
| `src/steamzero/ui/qml/sizes.js`, `tests/qml/check_storage_units.qml` | `WS-2026-09-RC01-STORAGE-UNITS` | 0 |
