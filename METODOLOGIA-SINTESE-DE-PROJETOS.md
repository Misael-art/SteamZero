# METODOLOGIA DE SÍNTESE DE PROJETOS
## Como cruzar N projetos existentes para planejar um produto que herda o melhor de cada um

**Público-alvo deste documento: um agente de IA.** Ele é autocontido: lendo apenas este arquivo, você deve conseguir replicar o processo completo para qualquer outro domínio (não só emulação). O projeto SteamZero (`/mnt/sdcard/Projects/Port_Steam/`) é a execução de referência — os caminhos citados como "exemplo real" apontam para artefatos concretos que você pode inspecionar como gabarito.

---

## 0. A ideia em uma frase

> Não se constrói um produto melhor copiando projetos existentes; constrói-se **auditando-os com evidência**, extraindo de cada um a sua força comprovada (cobertura, simplicidade, isolamento, robustez), registrando as fraquezas como anti-requisitos, e **documentando uma fundação completa antes de qualquer código** — com um gate de aprovação humana entre planejar e implementar.

## 1. Os cinco princípios do método (invariantes em qualquer domínio)

| # | Princípio | Regra operacional |
|---|---|---|
| MP-1 | **Documentação antes de implementação** | É proibido escrever código de produção antes da aprovação formal da fundação. A fase de estudo só pode: ler, catalogar, analisar estaticamente, documentar, diagramar, prototipar descartável. |
| MP-2 | **Evidência antes de afirmação** | Toda conclusão sobre um projeto-fonte cita: repositório, caminho, arquivo, função/linha, comportamento observado, impacto, recomendação. Nunca declarar que uma função existe pelo nome do arquivo — abrir e verificar implementação e callers. |
| MP-3 | **Fontes são somente-leitura** | Projetos-fonte jamais são modificados. Ausências locais são registradas, não presumidas; obter fontes externas só de forma **declarada** (nunca silenciosa) e apenas quando não há fonte local a substituir. |
| MP-4 | **Melhor base por capacidade, não por projeto** | O cruzamento é feito capacidade a capacidade (instalar, configurar, reverter, logar...), não projeto a projeto. Um projeto pode ser a melhor base em uma linha da matriz e o pior exemplo em outra. |
| MP-5 | **Licença antes de cópia** | Nenhuma linha é copiada antes de a matriz de licenças estar documentada e a licença do novo projeto decidida. Incompatível ou incerta ⇒ reimplementar por comportamento, nunca com o código-fonte lado a lado. |

## 2. Visão geral do pipeline (7 etapas)

```
E1 Descoberta ─► E2 Auditoria com evidência ─► E3 Cruzamento (matrizes)
      ─► E4 Análise legal ─► E5 Síntese arquitetural ─► E6 Fundação documental
      ─► E7 Relatório de prontidão + GATE humano ─► (só então) Implementação
```

Cada etapa tem **entradas, saídas e critério de conclusão**. Não avance com saída incompleta — registre a lacuna em `KNOWN-GAPS.md` e classifique-a (bloqueia o quê?).

---

## E1 — Descoberta e registro de fontes

**Entrada:** lista de projetos-fonte indicada pelo responsável + caminhos prováveis.

**Procedimento:**
1. Procurar cada projeto nos caminhos indicados; se não achar, buscar recursivamente por nome, estrutura, remotes git e conteúdo característico.
2. Para cada fonte encontrada: registrar caminho, commit/versão, remote, estado aparente (completo? submódulos ausentes?).
3. Para cada fonte **ausente**: registrar a ausência explicitamente. Se não existir fonte local a substituir, clonar a fonte oficial de forma **declarada** em um diretório `reference/` do novo projeto, somente-leitura, registrando commit e data. Se o clone for inviável (repo gigante), obter a árvore via API + arquivos representativos, e classificar como análise parcial.
4. Nunca presumir que um repositório está completo.

**Saída:** `docs/02-research/SOURCE-REPOSITORIES.md` + primeira entrada do `docs/WORKLOG.md`.
**Exemplo real:** neste projeto, EmuDeck/RetroDECK não existiam localmente — a ausência foi registrada e os clones declarados; `RetroDECK/components` excedeu timeout e virou lacuna G1 com plano de mitigação.

## E2 — Auditoria com evidência (por projeto)

**Objetivo:** entender o que cada projeto FAZ e COMO, com prova.

**Procedimento por projeto:**
1. Ler primeiro a auto-documentação (README, CLAUDE.md, docs internas, CI) — ela revela a intenção e a arquitetura declarada.
2. Inventariar artefatos por classe: scripts por linguagem, configs, manifests, templates, parsers, launchers, serviços, testes, CI, dependências, downloads externos, comandos privilegiados, dados persistidos. Use contagens reproduzíveis (`find`/`grep` registrados).
3. **Spot-checks de qualidade estrutural** (ajuste ao domínio; estes são os universais):
   - tratamento de erro: `grep -rl "set -euo pipefail" | wc -l` vs total de scripts; equivalentes em outras linguagens;
   - anti-padrões: `eval`, `curl|bash`, dispatch por string, escrita direta em arquivo crítico, downloads sem checksum, sudo em bloco;
   - padrões-ouro: escrita atômica, staging, backups, rollback, locks, validação de entrada, logs com permissão restrita, dry-run, idempotência.
4. Ler **integralmente** os 2–4 arquivos mais estruturais de cada projeto (a biblioteca comum, o entrypoint, o pipeline central) — é aí que a alma do projeto aparece. Ler por amostragem o resto.
5. Registrar cada achado com `arquivo:linha` (MP-2). Fraquezas viram **anti-requisitos nomeados** ("a classe de bug X do projeto Y fica proibida por design").

**Saída:** `docs/02-research/SCRIPT-INVENTORY.md`.
**Exemplo real:** "EmuDeck: 0/228 scripts com strict mode; download com SHA256 opcional em `helperFunctions.sh:743`; migração destrutiva em `emuDeckDuckStation.sh:24-30`" — cada um desses virou requisito no novo projeto.

## E3 — Cruzamento: as três matrizes

### 3a. Matriz de capacidades
Enumerar as capacidades do domínio (30±: instalação, atualização, configuração, dados do usuário, diagnóstico, UI, testes...). Para cada capacidade × cada projeto: `✔ implementado / ◐ parcial / ✖ ausente` **com evidência**, e três colunas de síntese: **Melhor base** (de quem herdar o conceito), **Lacunas** (o que ninguém tem), **Riscos**.

### 3b. Score de robustez (obrigatório ser numérico e justificado)
Não usar Low/Medium/High sem critério. Definir:
- critérios (12–15: erro, idempotência, atomicidade, backup, rollback, validação, logs, segurança, testes, portabilidade, manutenção, UX de falha, proteção de dados...);
- escala 0–4 por critério com âncoras objetivas (0=ausente ... 4=sistemático e testado);
- pesos somando 100, com os maiores pesos em segurança e proteção de dados;
- nota por célula **citando a evidência da E2**.
O resultado diz de qual projeto herdar **arquitetura de execução** vs **conteúdo de domínio** — frequentemente são projetos diferentes.

### 3c. Gap analysis e duplicações
- **Gaps estruturais:** o que NENHUM projeto entrega (é onde mora o valor do novo produto).
- **Duplicações entre e dentro dos projetos:** N scripts quase-clones ⇒ candidato a "1 engine + N manifests"; lógica repetida em 2 linguagens ⇒ decidir a linguagem núcleo por ADR.
- **Não-idempotências e efeitos colaterais observados** ⇒ lista de correções por design.

**Saída:** `CAPABILITY-MATRIX.md`, `ROBUSTNESS-SCORE.md`, `GAP-ANALYSIS.md`.
**Exemplo real:** scores 72/49/41/25 levaram à síntese "execução do PhaseZero + plataforma do RetroDECK + modularidade do LinuxToys + domínio do EmuDeck".

## E4 — Análise legal (antes de qualquer reuso)

1. Licença de cada projeto (arquivo LICENSE real, não suposição) e de componentes embarcados; projetos **sem licença** = all-rights-reserved por default (registrar como questão para o titular).
2. Matriz de compatibilidade: o que pode ser copiado sob qual licença do novo projeto (cenários).
3. **Bloqueio operativo:** até a licença do novo projeto ser decidida, zero cópia — e registrar isso como regra visível.
4. Política de reuso com árvore de decisão: licença conhecida? → compatível? → atende requisitos de segurança? → copiar com SPDX+atribuição; qualquer "não" → reimplementar por comportamento (sem código lado a lado, sem reproduzir estrutura idiossincrática).
5. Marcas e nomes dos projetos-fonte não são licenciados por licenças de código — não usar na identidade do produto.

**Saída:** `docs/11-legal/{LICENSE-MATRIX,ATTRIBUTION-PLAN,THIRD-PARTY-NOTICES,REUSE-POLICY}.md`.

## E5 — Síntese arquitetural

Regra de ouro: **a arquitetura nova resolve os gaps da E3 e proíbe os anti-padrões da E2, herdando cada conceito da sua melhor base.**

1. Desenhar camadas com fronteiras verificáveis por lint (quem pode importar quem; onde é a única porta de escrita em disco; onde é a única fronteira de privilégio).
2. Todo fluxo mutável passa por um **pipeline transacional** explícito (scan→plan→preview→backup→stage→apply→verify→activate→test→commit) com recuperação determinística documentada por modo de falha.
3. Enumerar **modos de falha** (FM-xx) com detecção, resposta e estado final garantido — a tabela de FMs é o coração da resiliência.
4. **Toda decisão com alternativas reais vira ADR** com: contexto, problema, alternativas, prós, contras, riscos, decisão, consequências, critérios de revisão futura. Decisões que dependem do responsável ficam como ADR "pendente de decisão" — nunca decididas silenciosamente pelo agente.
5. Decisões de tecnologia arriscadas (ex.: toolkit de UI) não se fecham por preferência: o ADR define um **protótipo-gate** com critérios mensuráveis e plano B orçado.

**Saída:** `docs/03-architecture/*` (10 docs) + `docs/adr/*`.

## E6 — Fundação documental completa

Estrutura-padrão (adapte nomes ao domínio, mantenha as 13 áreas):

```
docs/
├── 00-vision/      visão, princípios numerados (P-xx), NÃO-objetivos
├── 01-product/     PRD, personas, jornadas (com pontos de falha tratados),
│                   catálogo de features (com origem conceitual e fase),
│                   critérios de aceitação Given/When/Then (AC-xx)
├── 02-research/    (saídas de E1–E3)
├── 03-architecture/ (saídas de E5) incl. FAILURE-MODES e TRANSACTION-MODEL
├── 04-security/    threat model (ameaça→mitigação→verificação), requisitos
│                   verificáveis (SR-xx), path safety, supply chain, segredos,
│                   políticas de conteúdo/domínio, garantias de rollback
├── 05-data/        modelo de estado, schemas, versionamento de migrações,
│                   formato de backup
├── 06-api/         contratos CLI/API, catálogo de ERROS COM CÓDIGOS ESTÁVEIS,
│                   eventos/progresso, autorização
├── 07-ui-ux/       princípios, arquitetura de informação, specs por superfície,
│                   acessibilidade, UX de erro, wireframes ASCII
├── 08-testing/     estratégia, matriz funcionalidade×critério, INJEÇÃO DE
│                   FALHAS (FI-xx), matriz de hardware, testes de segurança
│                   (ST-xx) e de rollback (RT-xx) com protocolo de aprovação
├── 09-operations/  logging, diagnóstico, support bundle, canais, update/rollback,
│                   runbooks de recuperação
├── 10-migrations/  adoção de dados dos projetos-fonte SEM movimentação
│                   destrutiva (adoção por referência) + preservação de dados
├── 11-legal/       (saídas de E4)
├── 12-roadmap/     fases com critérios de saída, marcos com demonstração
│                   objetiva, RISCOS com prob×impacto e gatilho de revisão,
│                   dependências (decisórias e técnicas)
├── adr/            decisões numeradas
└── glossary/       vocabulário único do produto
```

Mais os quatro arquivos de honestidade, mantidos vivos:
- `WORKLOG.md` — diário com evidências por sessão;
- `OPEN-QUESTIONS.md` — decisões que pertencem ao humano (com opções e impacto de não decidir);
- `ASSUMPTIONS.md` — premissas + o que as invalida;
- `KNOWN-GAPS.md` — lacunas classificadas (bloqueiam o quê?).

**Regras de qualidade documental:**
- IDs estáveis e cruzáveis em tudo (P-xx, SR-xx, AC-xx, FM-xx, FI-xx, RT-xx, E-xx, R-xx, M-xx, G-xx, Q-xx) — é isso que permite rastreabilidade requisito→teste→código depois.
- Cada documento referencia os outros por esses IDs; contradições entre docs são bugs da fundação.
- Exemplos normativos (payloads JSON, mensagens de erro literais, wireframes) em vez de prosa vaga.

## E7 — Relatório de prontidão + gate humano

1. Produzir `FOUNDATION-READINESS-REPORT.md` com: resumo executivo, fontes analisadas, escopo coberto, lacunas, conclusão das matrizes, arquitetura recomendada, riscos críticos, licenças, backlog, roadmap, complexidade, dependências, **autoavaliação contra o checklist de aprovação**, itens bloqueadores e recomendação.
2. Classificar honestamente: `NOT READY / PARTIALLY READY / READY FOR PROTOTYPE / READY FOR IMPLEMENTATION`. Só a última quando todos os bloqueadores críticos estiverem resolvidos **documentalmente** — a existência dos arquivos não basta; avalie consistência, completude, ausência de contradições, testabilidade e viabilidade.
3. **PARAR.** A implementação só começa com um gate explícito (arquivo `APPROVED_TO_IMPLEMENT` no diretório do projeto ou autorização textual equivalente do responsável).

## E8 (pós-gate) — Handoff de implementação com revisão externa

O padrão de entrega para a fase de construção:
1. Escrever um **prompt de implementação** (exemplo real: `IMPLEMENTATION-PROMPT.md`) que: fixa a fundação como fonte da verdade; impõe Definition of Done por commit (teste junto, lint/tipos, golden files de contrato, rollback provado com kill, idempotência 2×); lista proibições que invalidam o trabalho; exige WORKLOG com evidências; e exige um `IMPLEMENTATION-REPORT.md` final com falhas listadas integralmente e autoavaliação do que o implementador NÃO confia.
2. Anunciar no próprio prompt que haverá **revisão externa independente** (reexecutar suíte, auditar requisitos no código, tentar quebrar o rollback) — implementadores que sabem que serão auditados relatam melhor.

---

## Apêndice A — Checklist de replicação (cole no seu plano e marque)

```
[ ] E1: fontes localizadas OU ausência registrada + referência declarada
[ ] E1: nada nas fontes foi modificado (verificado ao final: git status limpo nelas)
[ ] E2: inventário com contagens reproduzíveis por projeto
[ ] E2: spot-checks de anti-padrões e padrões-ouro com arquivo:linha
[ ] E2: 2–4 arquivos estruturais lidos integralmente por projeto
[ ] E3: matriz de capacidades com melhor-base/lacunas/riscos por linha
[ ] E3: score numérico com critérios, âncoras, pesos e justificativas
[ ] E3: gaps estruturais + duplicações + não-idempotências nomeados
[ ] E4: matriz de licenças + política de reuso + bloqueio operativo ativo
[ ] E5: fronteiras verificáveis + pipeline transacional + tabela de FMs
[ ] E5: ADRs com alternativas reais; decisões humanas marcadas pendentes
[ ] E6: 13 áreas documentais + 4 arquivos de honestidade + IDs cruzados
[ ] E7: relatório de prontidão com classificação honesta + PARADA no gate
[ ] E8: prompt de implementação com DoD + anúncio de revisão externa
```

## Apêndice B — Armadilhas observadas (aprenda com a execução de referência)

1. **Repo de referência gigante:** não insista em clone integral com timeout; árvore via API + amostras representativas + lacuna classificada resolve para planejamento.
2. **Projeto-fonte sem LICENSE:** não presuma permissão nem proibição — registre como questão do titular e siga com reimplementação-por-comportamento como plano seguro.
3. **A tentação de decidir pelo humano:** nome do produto, licença, orçamento de hardware e cadência de release são decisões do responsável. Documente opções e recomendação; nunca feche sozinho.
4. **Score qualitativo preguiçoso:** "High/Medium/Low" sem âncora não sobrevive a revisão; o esforço do score numérico se paga quando duas fontes disputam a mesma capacidade.
5. **Documentar o ideal, não o real:** as fraquezas do melhor projeto também entram (ex.: o rollback da execução de referência restaurava sem verificar — virou requisito RB-4 no novo design). O melhor projeto é a melhor base, não um gabarito perfeito.
6. **Fundação sem IDs:** prosa sem identificadores estáveis não conecta requisito→teste→código e apodrece na implementação.
7. **Escopo herdado por inércia:** projetos-fonte trazem funções fora do domínio (na referência: boot/VM/homelab). NON-GOALS explícitos salvam o roadmap.
```

**Fim da metodologia.** Para replicar: execute E1–E7 no novo domínio, produza os artefatos com os mesmos padrões de evidência e honestidade, pare no gate e entregue o handoff E8.
