# 125 — Preparação da intervenção no host no SHA consolidado (2026-09-30)

**Plano, não execução.** Nenhuma instalação, release, tag ou mutação de host foi feita nesta
rodada, e a autorização vigente (integração + fechamento documental) expressamente não as cobre.
Este arquivo substitui a pré-condição 1 do plano `62-preparacao-de-validacao-fisica.md` (mesmo
diretório da oitava rodada), que continuou válido em tudo o mais: cenários, separação
"prova / não prova", sanitização e limites de terceiros permanecem os daquele documento — não se
reproduzem aqui para não criar duas versões da mesma lista.

## 1. Estado das quatro pré-condições, re-medido

| # | pré-condição | quem decide | estado agora, com a medição |
|---|---|---|---|
| 1 | fileira integrada em `main` na ordem de ancestralidade | operador (merge) | **SATISFEITA.** `origin/main = 7808374257db3059c1934cb4be6007d8a749346e`; os nove merges são ancestrais diretos (`9fc1c594 · cba3fe42 · 67e30afc · 231ba4d3 · 5f6ff508 · c4385308 · 66b442b6 · cb71a527 · 78083742`); 8/8 checks obrigatórios `SUCCESS` por push nesse SHA (run 36689372443) |
| 2 | release construída do SHA integrado pelo fluxo governado | operador, `tools/release_host.py` | **PENDENTE.** O artefato que existe do SHA consolidado é o wheel do CI (`steamzero-2.0.0rc1-py3-none-any.whl`, sha256 `a1cd3709b73f151fd261370fa2ff13dcef564224ecf1efa20c253de6aa00eb5e`, proveniência `commit=7808374257db`, `sourceTreeState=clean`). **Isto não é a release governada**: AGENTS §4 proíbe esta frente construir artefato de release sem pedido |
| 3 | autorização específica de instalação, nomeando release, branch e sessão | operador | **PENDENTE.** Sem ela, o instalador nem é invocado; o token do `--confirm-install` é obtido e usado exatamente como o fluxo exigir |
| 4 | rollback conhecido antes da ativação | agente prepara, operador executa | **PREPARADO, NÃO RE-MEDIDO.** Última liberação registrada no acervo do repo: `2.0.0rc1-e2af2562ebba` (26/09, `HOST-INSTALL.md`/cartões da rodada 26). Valor declarado como anterior: o host físico não foi acessado nesta sessão. Antes de ativar, `ls -1 /opt/steamzero/releases` e confirmar qual delas é a `current` real |

## 2. Sequência que o operador autoriza ou recusa (nada disto foi executado)

1. `tools/release_host.py inspect --json` no SHA `7808374257db…` → conferir `--source-commit`
   completo, wheel, wheelhouse, entry points de boot e hash.
2. `verify-bundle` no bundle produzido; falha de autenticação, CI, hash, proveniência, convergência
   ou idempotência **encerra** o fluxo — não se continua por comando manual equivalente.
3. `install --source-commit 7808374257db… --rollback-release <current real lida no host>` com o
   token exibido. Só depois dos preflights da AGENTS §1.
4. Verificação read-only: `steamzero --version`, `doctor`, units, sessão ativa, `/proc/<pid>/exe`
   apontando para o `venv/bin` da release ativada, e o gate estável **também no rollback**.
5. Reinicialização física: ação exclusiva do operador, depois de declarada a prontidão.

## 3. Jornadas a executar no hardware (as mesmas de `62`, agora com SHA candidato)

Cinco jornadas, cada uma com o que estabelece e o que **não** estabelece, no artefato instalado do
SHA consolidado:

* **J1 dobra da Home** com as três superfícies de atenção acesas, em 1280×800 e escala do Deck —
  estabelece alcance físico do primeiro alvo acionável; não estabelece que `Pendências` está na dobra.
* **J2 prontidão legível** (página de Emulação com bloqueios reais) — estabelece que o contrato v2
  chega ao usuário; não estabelece performance (a cauda de ~11,4 s de `emulation` em `GET /status` é
  apenas cronometrada como observação, sem FPS/memória alegados — AGENTS §10).
* **J3 unidades de armazenamento** — a mesma grandeza (`1073741824 B`) nas quatro vistas, no locale
  do host; é a jornada que existe justamente porque `P` provado no wheel ainda não é `H`.
* **J4 respostas tardias** no RetroFE e no ES-DE, dentro do shell — fechar com pedido em voo,
  reabrir, deixar a resposta chegar; estabelece descarte do efeito sem escrever na superfície
  reaberta; **não** estabelece cancelamento do request (ele não é cancelado).
* **J5 erro controlado e recuperação** — recusar payload idêntico e ver a superfície voltar ao
  estado anterior com a bandeira de ocupado correta; degradação sem travar (AGENTS §8).

Capturas por AGENTS §9: `01-baseline.png`, `02-entrega-funcional.png`, `03-recuperacao.png` na
pasta de evidência do item, com sha256 registrado, execução com `HOME` e XDG temporários vazios
(precedente de sanitização: `docs/09-operations/HANDHELD-PHYSICAL-VALIDATION-2026-07-22.md`).
Nenhuma captura ou registro público leva acervo, conta, caminho pessoal ou nome do operador.

## 4. Itens que nenhuma execução no host resolve

* **Seletor nativo de diretório** — é a única linha que exige ambiente não-offscreen e, no host, é
  dirigível: a jornada precisa ser escrita antes de rodar, e uma rota por Enter continuará não
  promovendo a rota nativa.
* **Contraste** — 4,5:1 vs ≥7:1 é decisão de produto; medir no host não decide.
* **F-1 (`memoryGb` → bytes pelo formatador)** e as **cinco superfícies roláveis** ainda não
  medidas — trabalho de código, não de hardware.
