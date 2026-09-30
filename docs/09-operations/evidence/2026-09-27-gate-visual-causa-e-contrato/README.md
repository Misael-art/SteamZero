# Evidência — gate visual do PR 241: causa do vermelho, publicação de artefatos e contrato de captura

Lote: `WS-2026-09-RC01-READINESS-FOCUS` · branch `codex/rc01-readiness-focus-2026-09-27` · HEAD de partida
`3b0778fe` (= ponta remota no início da rodada) · run vermelho de referência `36333208783`
(job `Gate visual QML (Linux)`, id `108659002909`, `2 failed, 328 passed, 12 skipped, 6116 deselected in 1145.33s`).

Recorte desta rodada: **exclusivamente** o bloqueio visual do #241. Nenhum merge, nenhuma 4ª fatia.
**RC-01 não se encerra aqui** — a primeira dobra da Home e as demais pendências continuam com critérios próprios.

## As quatro respostas, separadas

| Pergunta | Resposta medida | Onde |
| --- | --- | --- |
| Por que o gate reprovou? | A imagem canônica do gate (`ghcr.io/…/steamzero-qml-visual@sha256:8b832ec1…`) tem `fc-list` = **0**: instala a pilha de texto (fontconfig/freetype/harfbuzz) e nenhuma fonte. Os dois gates de captura de diálogo herdavam o `fontconfig` do host via `os.environ.copy()`, então no host saía texto e no runner saía tofu. **Não há defeito de produto**: o diálogo renderiza certo nos dois viewports. | `01-…log` |
| Por que a evidência não chegava? | Duas causas independentes: o `path:` do upload procurava `/tmp/pytest-of-*/**` enquanto `tools/run_tests_isolated.py` realoca `TMPDIR` para `/tmp/steamzero-tests-*/tmp/…` (0 artefatos `qml-visual*` nos 100 últimos runs, e o aviso explícito no log do job); e o `TemporaryDirectory` é apagado ao sair, o que mataria até um glob certo. Corrigido publicando em `build/visual-evidence/` **antes** das asserções + `if-no-files-found: error`. | `03-…log` |
| O contrato de captura prestava? | Não. `st_size > 20_000` é proxy: um golden com **1 pixel** trocado tem 34 554 bytes e passava; a captura sem fonte do runner (7 147 B) reprova, mas o número não diz *o quê* falta. Substituído por decodificável + dimensão + não uniforme + regiões dentro da moldura + igualdade pixel a pixel com baseline versionada, sem tocar nos 13 casos de geometria/foco nem remover nada. | `02-…log` |
| Qual é a base real dos três PRs abertos? | Pilha linear `#239 ⊂ #240 ⊂ #241` sobre `main 3495c49d` (2 / 7 / 18 commits), todos com `base=main` e o mesmo merge-base. Ordem de integração sem duplicação: 239 → 240 → 241, em merge commit. | `08-…log` |

## Arquivos desta pasta

| Arquivo | Conteúdo |
| --- | --- |
| `00-preflight.log` | branch/HEAD/ponta remota, worktree único, processos de teste concorrentes e a correção de duas afirmações de rodadas anteriores (`git stash list` tem 5 entradas antigas; o vermelho não era "ambiente do runner" nem "corrida") |
| `01-causa-raiz-container-sem-fonte.log` | hipótese, reprodução na mesma imagem do CI em segundos, experimento de uma variável só (`FONTCONFIG_FILE`: `fc-list` 0→4, cena 1 de 7 147→31 184 bytes), tabela das cinco cenas, paridade sha256 host↔container, determinismo, inspeção das imagens e as hipóteses que caíram |
| `02-contrato-novo-e-provas-de-mordida.log` | por que o proxy é inadequado (incluindo a métrica de "cobertura de tinta" rejeitada por medição: 3,0 % sem fonte vs 2,4 % com fonte — o sinal inverte), o contrato novo, a tabela da sonda de mordida, o corte de regime por geometria e os limites honestos |
| `03-artefatos-do-runner.log` | as seis medições que fecham a causa da publicação, a correção no workflow e no teste, a verificação de privacidade do que é publicado e o que ainda não está provado |
| `04-sonda-de-mordida-do-contrato.txt` | saída literal da sonda: cada verificação contra fundo uniforme, a captura real do runner (este PNG desta pasta), golden com 1 pixel trocado, o golden correto, e a moldura por cena no corte de regime |
| `05-sonda-de-mordida.py` | o script que produz `04`, autocontido: só lê arquivos versionados e um `TemporaryDirectory`, sem depender de desta narrativa nem de caminho de host |
| `06-suite-visual-local.log` | resultado da suíte `-m visual` completa no ambiente isolado do projeto nesta rodada |
| `07-baselines-produzidas.log` | como os 9 baselines novos foram gerados, com o comando exato, o ambiente efetivo, a re-geração byte a byte e a limitação de que `make update-qml-goldens` não os cobre |
| `08-ancestralidade-e-ordem-de-integracao.log` | grafo medido de `#239 ⊂ #240 ⊂ #241` (2/7/18 commits acima de `main`, ancestralidade confirmada), a grade terminal dos três SHAs, por que #239/#240 estão verdes no mesmo gate e a ordem de integração que evita commits duplicados |
| `09-reexecucao-focada-na-arvore-final.log` | `67 passed` na árvore parada dos dois gates de diálogo + inventários de baseline, com o motivo explícito dos 10 desmarcados e a guarda de `$HOME` inalterado |
| `10-ci-723cfcde-verde-e-artefatos-conferidos.log` | a grade terminal do run `36341332344` (Gate visual **success**), a conferência arquivo por arquivo do artefato `qml-visual-artifacts` (51 arquivos / 36 PNG, as 9 capturas **byte idênticas** às baselines, varredura de privacidade com 0 ocorrências), e o vermelho residual dos três jobs de Python com a causa medida: o `scopeDigest` commitado estava velho para o conteúdo da pasta |
| `imagens/01-cena-1-no-container-sem-fonte.png` | 7 147 B, sha256 `c488b3c2…` — o render do CI: layout correto, todo glifo tofu |
| `imagens/02-cena-1-no-container-com-fonte-empacotada.png` | 31 184 B, sha256 `84080a23…` — mesma cena com a fonte empacotada; byte idêntica ao golden versionado |
| `imagens/03-cena-4-relatorio-extenso-sem-fonte.png` | 7 959 B, sha256 `36001b41…` — a cena mais densa em texto, menor que a cena 1 com fonte: tamanho não separa os casos |

## Como reproduzir

```bash
# 1) o vermelho, dentro da imagem fixada do CI (alguns segundos)
docker run --rm -v "$PWD:/work:ro" -v /tmp/gate-ci:/out -w /work \
  ghcr.io/misael-art/steamzero-qml-visual@sha256:8b832ec124ae72aa59a4de3b5c00ccf3f03b41a7e688f45c10daf767290041cd \
  bash -lc 'fc-list | wc -l; /usr/lib/qt6/bin/qml tests/qml/capture_esde_import_viewport.qml -- --output-dir=/out --label=ci'

# 2) a correção, mudando só o fontconfig para a fonte empacotada
#    (o que CanonicalEnvironment já faz e os dois gates agora usam)
.venv/bin/python -c "import sys; sys.path.insert(0,'tools'); from qml_capture_runner import CanonicalEnvironment; print(CanonicalEnvironment().to_env()['FONTCONFIG_FILE'])"

# 3) as provas de que o contrato morde
.venv/bin/python docs/09-operations/evidence/2026-09-27-gate-visual-causa-e-contrato/05-sonda-de-mordida.py
```

## Limites

* Nada aqui foi executado contra o app instalado (`2.0.0rc1-e2af2562ebba`) num viewport compacto real: o gate
  prova o **harness** no ambiente canônico. Pendência registrada em cartão.
* A publicação corrigida **está** confirmada: `10-ci-723cfcde-verde-e-artefatos-conferidos.log` confere
  o artefato `qml-visual-artifacts` do run `36341332344` arquivo por arquivo (51 arquivos / 36 PNG, as
  nove capturas byte idênticas às baselines versionadas). O que a corrida de `723cfcde` ainda reprovou
  foi o `STATUS-CHECK` dos três jobs de Python, por digest documental velho — causa e correção no mesmo
  log.
* Baselines pixel-exact são deliberadamente rígidas: trocar tema, fonte, freetype/harfbuzz ou DPI reprova, e a
  atualização é manual e explícita (o comando está em `07-baselines-produzidas.log`), nunca automática. O ambiente
  é fixado por digest de imagem e por `ci/qml-visual/environment.lock.json`, conferidos **antes** de renderizar.
  Estas nove baselines **não** são cobertas por `make update-qml-goldens`, que só conhece as dez fixtures planas.
* Caminhos temporários de execução aparecem como `<scratch>`/`<tmp>` nos arquivos desta pasta; nenhum caminho
  pessoal, token ou dado do acervo do host é publicado.
