# 31 — Identidade da árvore: o que cada leitura do checkpoint pina, de fato

Medição feita depois do checkpoint 24/25, motivada por um fato observado e não por
suspeita: reexecutar a leitura agregada hoje devolve **`6955ced9b824e33f`**, e as 14
leituras do voo devolviam **`f185438a112bc0b8`** — sem que nenhum arquivo de `src`,
`tests` ou `tools` tenha sido editado desde o fim das suítes.

Nada nos resultados do checkpoint muda com esta evidência: os rc, as contagens
(6 554 coletados na integral, 362 no gate visual) e os vereditos continuam os lidos
em `25-checkpoint-integral-e-gates.md`. O que muda é a **extensão da alegação** sobre
a identidade da árvore, que estava maior do que a leitura sustenta.

## 1. Causa, medida

`identidade()` (linha 31 de `24-gates-integrais.sh`) calcula

```
git ls-files -s src tests tools | sha256sum | cut -c1-16
```

`git ls-files -s` lê o **índice**, não a árvore de trabalho. No instante do
checkpoint, o código deste corte estava assim no índice (lido das próprias 14
leituras, bloco de `git status --short`, que é a única linha da identidade que enxerga
a árvore de trabalho):

| caminho | estado no voo | efeito na leitura agregada |
|---|---|---|
| `src/steamzero/ui/qml/ThemeEditorPanel.qml` | ` M` (modificado, não indexado) | ausente — o índice ainda apontava o blob de `af6a5c6e` |
| `tests/qml/check_shell_retrofe_import_late_response.qml` | `??` (não rastreado) | ausente — `ls-files -s` sem `-o` não lista não rastreados |
| `tests/integration/test_ui_shell_retrofe_import_late_response.py` | `??` | ausente, mesmo motivo |
| `tests/qml/check_shell_esde_import_dialog_journey.qml` | ` M` | ausente |

Ou seja: `f185438a112bc0b8` é o hash do índice em `af6a5c6e`, e `6955ced9b824e33f` é o
hash do índice depois de `dab12e95` + `6109fc54` + `690a1b84` moverem exatamente esses
caminhos para dentro. Os dois valores foram reproduzidos, não inferidos:

```
$ rtk proxy env GIT_OPTIONAL_LOCKS=0 GIT_INDEX_FILE=~/steamzero-retrofe-tmp/idx-af6a5c6e.tmp bash -c '
    rm -f "$GIT_INDEX_FILE"; git read-tree af6a5c6e
    git ls-files -s src tests tools | sha256sum | cut -c1-16'
f185438a112bc0b8          # = o valor das 14 leituras do voo
$ git ls-files -s src tests tools | sha256sum | cut -c1-16
6955ced9b824e33f          # = o valor de hoje, na cabeça 46fa4b29
```

O índice temporário vive fora do checkout e o índice real não foi escrito
(`git status --porcelain -- src tests tools` = vazio antes e depois).

## 2. O delta entre os dois hashes, caminho a caminho

Comparação par `(caminho → blob)` entre a árvore de `af6a5c6e` e o índice atual,
independente de ordem:

- entradas: 1 187 → 1 189;
- **adicionadas** (estavam `??` no voo): `tests/integration/test_ui_shell_retrofe_import_late_response.py`,
  `tests/qml/check_shell_retrofe_import_late_response.qml`;
- **blob trocado**: `src/steamzero/ui/qml/ThemeEditorPanel.qml`,
  `tests/qml/check_shell_esde_import_dialog_journey.qml`;
- removidas: nenhuma.

Contra-prova cruzada com um comando que não usa o índice:

```
$ git diff --name-only af6a5c6e HEAD -- src tests tools
src/steamzero/ui/qml/ThemeEditorPanel.qml
tests/integration/test_ui_shell_retrofe_import_late_response.py
tests/qml/check_shell_esde_import_dialog_journey.qml
tests/qml/check_shell_retrofe_import_late_response.qml
```

Os dois conjuntos coincidem (4 caminhos, mesmos nomes), e não há caminho fora deles.
Uma primeira versão desta comparação listou ~1 187 blobs "trocados"; era erro meu de
parser — `ls-tree` imprime `<mode> <tipo> <oid>` e `ls-files` imprime
`<mode> <oid> <stage>`, e ler os dois com o mesmo `split()` guardava a string literal
`"blob"` como OID. Registrado porque é o tipo de falso resultado que só aparece quando
a asserção é confrontada com o valor esperado.

## 3. O conteúdo testado é o conteúdo commitado

A leitura agregada não provava isso; as três linhas por arquivo provam, porque
`sha256sum` lê a árvore de trabalho:

| arquivo | valor no voo (14×) | valor hoje (árvore de trabalho) | HEAD (índice) |
|---|---|---|---|
| `ThemeEditorPanel.qml` | `bddd117ac33fcbcf…` | `bddd117ac33fcbcf` | idêntico |
| `check_shell_retrofe_import_late_response.qml` | `bc9d76d646685e20…` | `bc9d76d646685e20` | idêntico |
| `test_ui_shell_retrofe_import_late_response.py` | `0cb7744eff344587…` | `0cb7744eff344587` | idêntico |

Com `git status --porcelain -- src tests tools` vazio, a árvore de trabalho atual é
igual a `HEAD` nesses três topos. Logo, o que as suítes executaram é o que está
commitado em `46fa4b29`, e a alegação de conteúdo do checkpoint se mantém — por outra
leitura, não pela agregada.

## 4. Limite que passa a ficar declarado (não é retroativo)

O que as 14 leituras de `identidade()` sustentam, cada uma no seu alcance:

1. `branch` + `HEAD` idênticos: nenhum commit entrou durante o voo. **Sustentado.**
2. `git status --short` com as mesmas 13 linhas: nenhum caminho passou de limpo a
   sujo, de sujo a limpo, de não rastreado a rastreado, e nenhum `git add` ocorreu.
   **Sustentado.**
3. `sha256 src+tests+tools` (índice): nada foi **indexado** durante o voo.
   **Sustentado** — e é só isso.
4. As três linhas por arquivo: o conteúdo dos três arquivos que este corte altera não
   mudou durante o voo. **Sustentado.**

O que **nenhuma** dessas leituras sustenta: que uma edição de conteúdo em um
*quarto* arquivo rastreado (fora dos três pinados) teria aparecido. Ela não moveria o
hash do índice e não mudaria a linha de `status` desse arquivo, que já era ` M` ou já
existiria. A prova de congelamento deste lote é, portanto, **por arquivo
monitorado**, e não global sobre `src+tests+tools`.

Nada observado indica que tal edição tenha ocorrido — o oposto: `git diff` entre a base
e a cabeça contém exatamente os quatro caminhos da seção 2, então não há quinto arquivo
com conteúdo divergente nesta branch. A correção aqui é de alcance de alegação, não de
resultado.

## 5. Precedente e a leitura que entra no próximo checkpoint

O mesmo `git ls-files -s` foi usado no lote anterior
(`2026-09-28-rc01-storage-units/27-gates-integrais.sh`, valor `fff1806fe884d74a`): a
limitação é herdada do precedente, não introduzida por este corte. Nenhuma linha de
`24-gates-integrais.sh` ou `25-checkpoint-integral-e-gates.md` comitados foi reescrita
para refletir isto — histórico publicado não se edita; a correção entra nesta evidência
nova.

As duas candidatas a leitura agregada foram postas à prova num repositório descartável
fora do checkout (`~/steamzero-retrofe-tmp/idtest`, dois arquivos rastreados, nada do
projeto envolvido):

```
C = git ls-files -c -o --exclude-standard src | xargs -r sha256sum | sha256sum
A = git ls-files -s -o --exclude-standard src | sha256sum
```

| situação | `A` (índice, método do voo) | `C` (conteúdo de trabalho) |
|---|---|---|
| base | `629b9bfdcf25e1cd` | `a3d761d249f94562` |
| conteúdo de `src/f.py` editado, sem `git add` | `629b9bfdcf25e1cd` — **não se move** | `e73e6eb428131e7d` — move |
| restaurado com `git reset --hard` | `629b9bfdcf25e1cd` | `a3d761d249f94562` — volta ao valor da base |
| arquivo novo não rastreado (`??`) | `61479bd8fce75ace` — move | `a92d8ecacffba1fb` — move |
| arquivo novo removido | `629b9bfdcf25e1cd` | `a3d761d249f94562` |

Leitura que passa a valer no próximo checkpoint (oitavo elo): **`C`**, porque é a única
sensível à edição de conteúdo sem indexação — exatamente o buraco da seção 4. `A` não é
cega a arquivo novo (a última linha da tabela corrige uma inferência minha inicial: ela
lista não rastreados mesmo sem OID, e o hash se move); a cegueira de `A` é
especificamente sobre **conteúdo modificado e não indexado**.

Valor de referência de `C` neste checkout na cabeça `46fa4b29`
(`src tests tools`, com não rastreados): `ad7230a5a741e1b5`. É o número que o próximo
checkpoint deve reencontrar se nada de conteúdo se mover entre os dois voos.

**Divergência de leitura registrada, sem causa estabelecida:** na primeira execução
desta bateria, a linha "arquivo novo não rastreado" saiu com `A = 629b9bfdcf25e1cd`
(identico à base) e `C = a92d8ecacffba1fb`. Re-medida três vezes com os mesmos dois
canudos, `A` deu `61479bd8fce75ace` nas três. Duas causas candidatas foram testadas e
**recusadas**: (i) ordem de avaliação dentro do `echo` — as duas substituições rodam
depois do `printf`; (ii) `git reset --hard` anterior deixar obsoleta a listagem de não
rastreados — reproduzido em `~/steamzero-retrofe-tmp/idtest2` com `reset --hard` entre os
passos, e `A` se moveu normalmente (`2a3772b852da0797`, que difere de `61479bd8…` só
porque o arquivo chamava `novo2.py`). Git do host: `2.55.0`. Fica como anomalia de
leitura com comando, caminho e hash preservadas, não como propriedade do método: a
conclusão da tabela repousa nas três re-medicações concordantes.

