# 62 — Preparação da validação física do conjunto integrado (RC-01)

**Isto é um plano, não uma execução.** Nenhuma instalação foi feita nem presumida. AGENTS §1:
instalar no host exige autorização explícita do operador na thread atual, para a release e a
sessão indicadas, e o token exato mostrado pelo comando; autorização não se transfere.

## Pré-condições (todas externas, na ordem)

| # | pré-condição | quem decide | evidência exigida antes de prosseguir |
|---|---|---|---|
| 1 | a fileira #239 → #246 estar **integrada** na ordem de ancestralidade | operador (merge) | `git rev-parse origin/main` != `3495c49d…` e `git merge-base --is-ancestor <cabeça> origin/main` verdadeiro para as oito cabeças |
| 2 | release construída do SHA integrado, pelo fluxo governado | operador (`tools/release_host.py`), §4 proíbe a frente construir artefato sem pedido | `inspect --json` + `verify-bundle` no bundle, com `--source-commit` completo e hash conferido |
| 3 | **autorização específica de instalação**, nomeando release, branch e sessão | operador | texto da autorização nesta thread; o token do `--confirm-install` é obtido e usado exatamente como o fluxo exigir |
| 4 | rollback conhecido antes da ativação | agente prepara, operador executa | `--rollback-release` apontando para a release atualmente ativa (`2.0.0rc1-e2af2562ebba`) |

## O que o plano mede, critério a critério

Cada linha diz **o que a prova no host estabelece** e **o que ela não estabelece** — a
segunda coluna existe porque a experiência física não promove contrato, e vice-versa.

| cenário físico | como | prova | não prova |
|---|---|---|---|
| Dobra da Home com as três superfícies de atenção acesas (faixa + banner + cartão do mesmo código) | abrir a central com `/status` recusado real (rede cortada depois do primeiro carregamento, para os dados já existirem), painel interno 1280×800 e escala do Deck | o primeiro alvo acionável cabe inteiro na dobra **em pixels físicos**, com o compositor real, não offscreen | que o agregado continua valendo em outra resolução; que `Pendências` está na dobra (não está — 581/597 px contra banda de 493 px) |
| "Ver detalhes" devolve a prosa completa | toque/teclado real no cartão compacto, antes e depois | compactar não apaga, no compositor com fonte e hinting reais | o contrato de geração do ES-DE (outro eixo) |
| Alvos de 48 px | régua do compositor (captura + geometria) no cartão, na faixa e no rodapé do diálogo | alcance com dedo/analógico | as cinco superfícies roláveis ainda não medidas (`Emulation.qml`, `SectionNavigator.qml`, `SteamGameplay.qml`, os dois diálogos do painel) |
| Prontidão legível, causa e próxima ação visíveis | página de Emulação com bloqueios reais | que o contrato v2 chega ao usuário, não só ao harness | perf: a cauda de ~11,4 s de `emulation` em `GET /status` é medida aqui, mas só como observação cronometrada, sem afirmar FPS/memória (AGENTS §10 exige medição explícita) |
| Unidades de armazenamento | comparar a mesma grandeza (`1073741824 B`) nas quatro páginas, no locale do host | convergência no artefato instalado, com `sizes.js` realmente empacotado | nada — esta linha existe justamente porque `P` provado no wheel ainda não é `H` |
| Respostas tardias e recuperação no RetroFE e (quando (b) sair) ES-DE | fechar o diálogo com pedido em voo, reabrir, deixar a resposta chegar | que o efeito descartado não escreve na superfície reaberta, na janela real | que o request em voo foi cancelado — ele **não** é cancelado |
| Erro controlado e recuperação | recusar payload idêntico, ver a superfície voltar ao estado anterior com a bandeira de ocupado correta | degradação sem travar (AGENTS §8) | que nenhum caminho de boot foi afetado — isso é a checagem de baixo |
| Boot/sessão | leitura read-only: `steamzero --version`, `doctor`, units, sessão ativa | que a release ativa é a esperada e que o pior caso continua greeter utilizável | nada sobre UI; é o piso de segurança |

## Capturas e privacidade

AGENTS §9: cada etapa fisicamente entregue leva ao menos uma captura PNG funcional real, mais
erro e recuperação quando aplicáveis, nomeadas `01-baseline.png`, `02-entrega-funcional.png`,
`03-recuperacao.png` na pasta de evidência do item, com sha256 registrado. Precedente de
sanitização a seguir: `docs/09-operations/HANDHELD-PHYSICAL-VALIDATION-2026-07-22.md` — execução
com `HOME` e XDG temporários e vazios, para nenhuma captura conter acervo, conta, caminho
pessoal ou nome do operador. Nenhum registro público deste repo redistribui caminho pessoal
(o lote `47`/`52`/`55` acima aplica a mesma redação e declara os hashes pré e pós).

## Limites que este plano declara antes de rodar

* **Entrada humana:** toque, analógico e teclado virtual não são simuláveis de forma honesta por
  agente; a referência de 22/07 separou explicitamente "renderização nos outputs" de "entrada
  física", e esta mantém a separação.
* **Seletor nativo de diretório:** é o único item cuja prova **exige** ambiente não-offscreen. A
  porta por Enter funciona e é testada; isso **não** promove o diálogo nativo, que sob offscreen
  entrega `contentItem` nulo, sem `accepted` nem `rejected`. No host ele é dirigível — e só ali.
* **Contraste:** o conflito de política (4,5:1 vs ≥7:1) é decisão do operador. Medir no host não
  decide nada; decide a política escolhida.
* **Nada de terceiros:** o plano não toca ROM, BIOS, saves, GRUB, boot, units alheias ou
  configuração de terceiros (`/etc/sddm.conf` etc.). Instalação é exclusivamente o fluxo
  governado `tools/release_host.py`, com os preflights de §1 (branch/commit, gates, wheel de
  fonte commitada, ownership verificado, rollback conhecido).
* **Reboot físico** é ação do operador, depois de o agente declarar o host pronto para o teste.

## Bloqueio externo concreto

Hoje o plano não tem como começar: depende das pré-condições 1 a 3, todas do operador. Enquanto
`origin/main` for `3495c49d…`, a coluna **H** da tabela de `61-reconcilio-rc01-oito-elos.md`
continua "não" para os treze critérios, com razão.
