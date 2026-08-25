# Contexto de continuidade — SteamZero

Você assume o desenvolvimento contínuo do SteamZero. Leia este documento inteiro
antes do primeiro comando.

## 0. Onde você está

```
cwd absoluto: /mnt/sdcard/Projects/Port_Steam
```

Confirme com `pwd` e `git log --oneline -1` antes de qualquer coisa. Este repo já
foi confundido com outro projeto por um agente anterior, que auditou a árvore
errada e reportou conclusões falsas. Se `git remote -v` não mostrar
`Misael-art/SteamZero`, pare.

O host onde tudo é validado **é um Steam Deck LCD real** (Valve Jupiter), o mesmo
onde este repo está. Não existe "falta hardware Deck" como desculpa: uma auditoria
anterior errou exatamente nisso.

## 1. Leia primeiro, sem exceção

1. `AGENTS.md` — governança. Cada regra existe por causa de um incidente real.
2. `docs/STATUS.md` — visão gerada; a fonte de verdade são os JSON em
   `docs/status/items/`.
3. `docs/ACTIVE-WORK.md` — workstreams ativos e caminhos exclusivos. Consulte
   ANTES de criar branch ou tocar arquivo compartilhado.
4. `docs/01-product/AURA-SURFACES.md` e `docs/01-product/THEME-ENGINE-AND-STUDIO.md`
   — obrigatórios antes de mexer em tema, UI, launcher, scene graph ou efeito.

**AURA UI, AURA Launcher, Theme Engine e Theme Studio são quatro capacidades
independentes.** Provar uma NUNCA promove outra. Este erro já foi cometido.

## 2. Estado real em 2026-08-25

Este bloco envelhece. Reconfira cada linha antes de confiar nela.

- `main` local = `71d6998` (evidência física do `detail` em componente degradado),
  fast-forward a partir de `92d91d6`, working tree limpo.
- **Confira se `origin/main` já recebeu o `71d6998`.** O push foi bloqueado pelo
  classificador do harness e ficou a cargo do operador. Rode
  `git rev-list --count origin/main..main`: se devolver `1`, o push ainda não
  aconteceu e a entrega física seguinte está travada, porque `release prepare`
  recusa branch e o CI só gera run de push em `main`/tags.
- Release instalada e ativa no host: **`2.0.0rc1-92d91d631b80`**.
- Rollback disponível: `2.0.0rc1-2a1b0fb90105`.
- Suíte integral no commit atual: **5254 passed, 44 skipped, exit 0** (~29 min).

São **38 itens**. Distribuição honesta:

| Situação | Qtd | Significado |
|---|---|---|
| `verification: none` | 15 | Sem prova nenhuma (12 são agregadores de diretório) |
| `verification: unit` | 12 | Só teste unitário; nada provado no host |
| `verification: dev/vm` | 6 | Provado em dev ou VM |
| `verification: hw` | 5 | Provado no host real |
| `distribution: not-packaged` | 22 | Nem chegou a release instalável |
| `implementation: planned` | 4 | Não existe código: P2P, RetroAchievements, cast internet, LaunchBox |

Cuidado com a leitura de `implementation: complete`: significa "código escrito",
não "funciona". Um item pode estar `complete` com `verification: unit` ao lado.

**Não prometa "todos os emuladores com todas as opções funcionando".** O item
`SZ-EMULATION-ENHANCEMENTS` registra que a emulação foi historicamente Switch-only,
e `SZ-CONTROLS-INPUT-PROFILES` diz literalmente que perfis de controle ainda
precisam provar "efeito observável". Trate cada afirmação como não-provada até
haver evidência física.

## 3. Os quatro gates, mais dois

Depois de CADA item, não só no fim:

```bash
.venv/bin/python tools/run_tests_isolated.py tests -q
.venv/bin/ruff check src tools tests
.venv/bin/ruff format --check src tools tests
.venv/bin/mypy src
make independence boundaries
make status-check
```

- `ruff check` **não** cobre formatação. O CI já reformatou um PR sozinho porque o
  agente pulou `ruff format --check`.
- Cobertura não regride. Nunca enfraqueça nem apague um teste para passar.
- **Nada em paralelo enquanto a suíte roda** — o gate mede o state home real e
  execuções concorrentes contaminam a atribuição. Se o daemon estiver ativo, o
  guard avisa que a atribuição está degradada; para rigor total, pare o daemon.
- Rodando de worktree, force `PYTHONPATH` para o `src` do worktree: por padrão os
  gates importam o `src` do checkout principal e você testa o código errado.
- Sempre confira o exit code explicitamente. Um relatório de agente já declarou
  "ruff verde" estando vermelho.

## 4. Autorizações — o que você NÃO pode fazer sozinho

Proibido por padrão: `sudo`, `bigsudo` para comando arbitrário, `steamzero-host`
para mutação, editar `/opt/steamzero`, `/usr/local`, `/etc`, `/boot`.

**Instalar ou reverter release exige autorização explícita do operador na thread
atual**, válida só para aquela release/branch/sessão. O caminho é
`tools/release_host.py` (nunca `install_host.py` manual).

> **Observação prática, medida em 2026-08-25.** O classificador de permissões do
> harness **bloqueia duas ações mesmo depois de o operador autorizar**:
>
> 1. `tools/release_host.py install` — bloqueado em 4 tentativas seguidas.
> 2. `git push` — bloqueado inclusive para push normal de fast-forward.
>
> A mensagem diz explicitamente que "isn't about the action itself": é um gate do
> harness, não uma recusa de governança. **Não tente contornar** — nem por
> `bigsudo install_host.py` manual, nem por remote/refspec alternativo. Faça o
> trabalho todo até o commit local e entregue ao operador a linha exata pronta
> para colar. Gastar tentativas redescobrindo isso é desperdício.
>
> Fluxo do install: rodar com `--confirm-install PENDING`, que falha de propósito
> e imprime o token exigido, e repetir com o token impresso.
>
> Depois que o operador executar, **verifique você mesmo** em vez de aceitar o
> relato: `readlink -f /opt/steamzero/current`, `steamzero --version` e o
> `service.generation` do doctor.

Push, publicação, instalação e rollback **não** são implicitamente autorizados.
Sem autorização: conclua até os gates e o commit local, registre o bloqueio exato,
e **não simule nem alegue entrega física**.

Reboot é sempre ação do operador.

## 5. Ciclo obrigatório por item

1. Reproduza o defeito ou registre baseline verificável.
2. Causa raiz e a menor correção completa.
3. Testes focados durante a investigação; gates integrais só no fechamento.
4. Commit funcional isolado.
5. Push só da sua branch, se autorizado. **Nunca force push.**
6. Instalação no host só conforme a autorização e o token.
7. Valide no artefato instalado: sucesso, erro, recuperação, idempotência,
   preservação de dados e versão efetivamente ativa.
8. Evidência física, item de status, `make status-check`, regenerar `STATUS.md` e
   `ACTIVE-WORK.md`, commit documental isolado, e só então acrescentar o
   fechamento ao `docs/WORKLOG.md` (append-only; nunca edite sessão anterior).
9. Próximo item elegível, imediatamente.

Um item cuja validação física falhou **permanece aberto** e volta ao passo 1. Não
avance só porque o teste automatizado passou.

Evidência PNG numerada (`01-baseline.png`, `02-entrega-funcional.png`,
`03-recuperacao.png`) em `docs/09-operations/evidence/<data>-<slug>/`, com a
release ativa visível. Se a correção não tiver superfície gráfica, diga isso no
README em vez de produzir uma captura decorativa — e nunca apresente renderização
de terminal como se fosse captura de tela.

## 6. Armadilhas já pagas com tempo

- `doctor` sai **1 só em `failed`**. `degraded` com `warn` sai **0**. Um fake de
  teste que saía 0 escondeu defeito do instalador por dois ciclos.
- `component apply` roda no daemon, cuja unit fixa `RestrictAddressFamilies=AF_UNIX`.
  **O install governado não baixa nada.** O mesmo argv funciona fora do daemon.
  Sintoma correlato já visto: `E-API-GENERATION-MISMATCH`.
- Depois de instalar, confirme `service.generation` no doctor. Sem o daemon na
  geração nova, o `component status` responde pelo código antigo e sua evidência
  inteira é inválida.
- Autoconfig do RetroArch Flatpak: o diretório declarado é interno ao sandbox.
  Abrir o emulador **não** destrava.
- Ref Flatpak é o ID do app; `_REF_RE` rejeita barras.
- `release prepare` recusa branch: o CI só gera run de push em `main`/tags, então
  **merge em `main` é pré-requisito da entrega física**.
- Sonda de UI já produziu falso positivo 4 vezes. Derrube os falsos antes de
  publicar qualquer contagem.
- Classificar ação de UI pela forma inventa controles que não existem; só sonda
  comportamental prova no-op.
- Arquivos gitignored perdidos no checkout principal já reprovaram 2 testes e o
  `status-check` sem relação com o trabalho em curso.
- Enums de `docs/status/items/*.json` são estritos: `operation` aceita
  `unknown|blocked|degraded|ready` e `evidence.kind` aceita `hardware`, não
  `physical`. Inventar valor reprova no `status-check`.

## 7. Fila priorizada

Faça na ordem. Cada bloco depende do anterior.

**P0 — destravar a entrega física.** `SZ-EMULATION-ENHANCEMENTS` documenta que o
install governado nunca baixa (item 6 acima). Enquanto isso não for corrigido em
`tools/install_host.py`, nenhum emulador pode ser instalado pelo fluxo governado, e
toda promessa de "emuladores funcionando" é vazia.

**P1 — matriz física dos componentes.** `SZ-COMPONENT-LIFECYCLE` e
`SZ-EMULATION-M10`: install/verify/rollback de emulador real no host, incluindo o
smoke flatpak-info do melonDS, que é o próximo pendente de
`SZ-EMULATION-LONG-OPERATIONS`.

**P2 — controles.** `SZ-CONTROLS-INPUT-PROFILES` com controle físico conectado:
resolver índice, escrever autoconfig gerenciado só quando ausente (marcador
obrigatório, jamais editar o `retroarch.cfg` do usuário) e provar que o perfil
chega ao RetroArch pelo lançamento governado.

**P3 — biblioteca canônica.** `SZ-LIBRARY-CANONICAL`: 138 diretórios do acervo sem
manifesto de plataforma. Decida suporte ou não-suporte explicitamente; troque a
amostragem do fallback por varredura completa.

**P4 — Launcher e temas no host.** `SZ-AURA-LAUNCHER` nunca teve evidência física.
`SZ-THEME-ENGINE`/`SZ-THEME-STUDIO` estão em `hw` mas `degraded`; o Studio hoje é
somente leitura. Toda afirmação de FPS, GPU ou memória exige medição no hardware —
teste offscreen não serve.

**P5 — UI.** `SZ-UI-DESKTOP-AUDIT`: fechar contraste, depois escalas, resoluções e
movimento reduzido, e provar na release instalada.

**P6 — frontends.** ES-DE, RetroFE, SRM e Steam shortcuts, cada um contra
instalação real.

Deixe por último `SZ-V2-HARMONIZED-FUNCTIONAL-RELEASE` — é o guarda-chuva da 2.0.0
e só fecha quando os anteriores tiverem prova própria. Os 4 itens `planned` não
começam sem ADR e decisão de produto.

## 8. Independência (ADR-0019)

Os projetos de referência foram **apenas pesquisa**. Nenhuma referência em código,
string de UI, unit, path, marcador — nem em comentário. Leia o ADR-0019 em
`docs/adr/` para a lista exata. `make independence` exige a AUSÊNCIA e varre
`src/steamzero/**/*.py` mais o `pyproject.toml`.

## 9. Como se comunicar

Execução autônoma: definidos item, branch e autorizações, avance sem perguntar
entre etapas. Atualizações curtas com resultado observado, bloqueio concreto e
próxima ação.

Pause só por dependência externa real: autorização ausente, token, ação física do
operador, segredo indisponível, ambiguidade material de produto ou risco
destrutivo. Havendo outro item seguro e independente, registre o bloqueio e siga
nele.

Relatório final: tabela item→commit→testes que provam; o que ficou fora e por quê;
ações de host, release ativa e rollback; e o que ainda exige o operador.

**Diga o que falhou.** Se o teste reprovou, mostre a saída. Se pulou etapa, diga.
Não declare pronto o que não observou funcionando.
