================================================================================
UX-03 — PASSADA DOCUMENTAL DEPOIS DO CHECKPOINT 10: o que mudou, por que a
        revalidação é proporcional, e onde o veredito verde é lido
Lote: rc01-readiness-semantics-2026-09-28 · Data: 2026-09-28 (16:07–16:20)
================================================================================

1. O PONTO DE PARTIDA
--------------------------------------------------------------------------------
A suíte integral única rodou na árvore congelada de 29 arquivos (HEAD `5d95034b`,
árvore git `4b23b239`, guard com `diff` vazio depois da execução) e terminou com
`1 failed, 6483 passed, 47 skipped in 2071.39s`. A falha é o gate de catálogo:

  - 33 itens com `scopeDigest` obsoleto;
  - `docs/06-api/JSON-SCHEMAS.md` alterado sem item de status responsável;
  - `docs/ACTIVE-WORK.md` e `docs/status/COVERAGE.md` desatualizados.

A causa está medida em `10-atribuicao-digests.log`: 33 de 33 itens reprovados
contêm ao menos um arquivo desta frente no escopo, 0 de 33 reprovam por
obsolescência anterior. Consequência assumida: renovar esses 33 digests é
atribuição desta frente.


2. O QUE A PASSADA DOCUMENTAL MUDOU, ARQUIVO POR ARQUIVO
--------------------------------------------------------------------------------
Somente documentação. Nenhum arquivo de `src/`, `tests/` ou `tools/` foi tocado
depois do congelamento do checkpoint 10.

  `docs/09-operations/evidence/2026-09-28-rc01-readiness-semantics/`
    Logs `10-*` (identidade da árvore, suíte integral com anotação, gates,
    catálogo, atribuição dos digests), `README.md` do lote e este arquivo.
    Apagados: `06-congelamento-lista.txt`, `06-congelamento-sha256.txt` e
    `06-suíte-integral.log` — congelaram a árvore pré-rodada 4 e uma suíte
    interrompida aos 26% sem veredito.

  `docs/status/items/ui-desktop-audit.json`
    +6 caminhos em `scopePaths` (`src/steamzero/domain/readiness.py`,
    `src/steamzero/ui/qml/readiness.js`, `tests/qml/readiness_fixture.js`,
    `tests/qml/check_readiness_surface.qml`, `docs/06-api/JSON-SCHEMAS.md`,
    `docs/09-operations/evidence/2026-09-28-rc01-readiness-semantics`);
    `WS-2026-09-RC01-READINESS-SEMANTICS` em `activeWorkstreams`;
    `GAP-UI-QML-JS-NAO-PROVADO-DENTRO-DO-WHEEL-DO-CI` em `knownGaps`;
    +4 critérios de aceitação (guard `READY_BASES`, lista de bloqueios atravessando
    a fronteira `QVariantList`, tinta do cabeçalho/glifo vindo do estado publicado,
    próxima ação não reimpressa como bloqueio);
    +5 entradas de evidência (rodadas 3 e 4, log de alcance/guard/empacotamento,
    checkpoint 10, e o vermelho do catálogo com a atribuição — registrado com
    `result: failed`, porque foi isso que ele foi);
    `nextAction` e `updatedAt` refeitos.

  `docs/status/workstreams/rc01-readiness-semantics-2026-09-28.json`
    `nextAction` reescrito: a versão anterior descrevia o plano de antes de codar
    e já não era verdade.

  `docs/WORKLOG.md`
    Uma sessão de fechamento ACRESCENTADA ao fim. Incidente registrado aqui
    mesmo, porque a regra é append-only e a violação foi minha: um `sed -i` sem
    âncora de linha aplicado ao arquivo inteiro para corrigir três typos do meu
    próprio bloco reescreveu **8 linhas de sessões anteriores** (a palavra
    "promovida" virou "promovidas"). As 8 linhas foram restauradas ao conteúdo
    original, uma a uma, por número de linha, e o gate do próprio projeto confirma:
    `check_worklog_append_only()` → OK, e `git diff --numstat` do arquivo é
    `94 0` (noventa e quatro acréscimos, zero remoções). Lição gravada: correção de
    texto num documento append-only se faz por linha, nunca por busca global.

  `docs/STATUS.md`, `docs/ACTIVE-WORK.md`, `docs/status/COVERAGE.md`
    Regravados por `tools/project_status.py render --write` (visões geradas; nunca
    editadas à mão). Diff: ACTIVE-WORK 1/0, STATUS 1/1, COVERAGE 4/4.

  33 cartões em `docs/status/items/`
    `scopeDigest` renovado, cada um a partir do valor **impresso pelo próprio
    `tools/project_status.py digest --item <ID>`** — nada transcrito de memória e
    nada calculado por outra ferramenta.


3. POR QUE O VEREDITO VERDE E A TABELA DE DIGESTS NÃO ESTÃO NESTA PASTA
--------------------------------------------------------------------------------
É um ponto fixo, medido, não uma conveniência. `scope_digest()`
(`tools/project_status.py:105`) calcula o digest sobre o **conteúdo atual** dos
arquivos do escopo, e `docs/09-operations/evidence/2026-09-28-rc01-readiness-semantics`
entrou no escopo de `SZ-UI-DESKTOP-AUDIT`. Portanto:

  - escrever um arquivo aqui **depois** de renovar o digest re-envelhece o digest;
  - gravar a tabela antigo→novo ou a saída verde de `make status-check` nesta
    pasta exigiria renovar o digest outra vez, o que mudaria o cartão, o que
    … (não converge).

A renovação é então a **última** escrita da árvore, e o que ela produz de verde é
lido onde não realimenta o digest:

  - a tabela `item → digest antigo → digest novo` vai na **mensagem do commit
    documental**, que é Git e é imutável;
  - o veredito final de `make status-check` e da suíte integral no SHA enviado vai
    no **corpo do PR e no CI daquele SHA**.

Declaro o limite sem rodeios: o verde de `make status-check` desta passada foi
executado na árvore **já modificada pela passada documental**, e é por isso que a
árvore do checkpoint 10 (§1) não é mais a árvore atual. A revalidação proporcional
a uma mudança exclusivamente documental é o gate que falhou — `make status-check` e
`tests/unit/test_project_status.py`, reexecutados depois da passada. A integral de
34 minutos não foi rodada de novo localmente porque o CI a roda por inteiro no SHA
final deste lote, e é aquele veredito que declaro como resultado integral da
entrega.


4. GATES REEXECUTADOS DEPOIS DA PASSADA (aqui sim, porque não alimentam digest)
--------------------------------------------------------------------------------
Comando, árvore e saída ficam no log do checkpoint 10; os reexecutados agora são
registrados na mensagem do commit e no corpo do PR. Ordem:

  1. `tools/project_status.py render --write`
  2. `tools/project_status.py digest --item <33 IDs>` → valores colhidos
  3. escrever os 33 `scopeDigest` nos cartões (última escrita da árvore)
  4. `make status-check` → veredito
  5. `tests/unit/test_project_status.py` → veredito
  6. `ruff check src tools tests` e `ruff format --check src tools tests` sobre os
     JSON/documentos (o `ruff` não alcança `.md`, mas alcança `.json`? não — roda
     sobre `src tools tests`; os cartões não são cobertos, então nada a refazer)
