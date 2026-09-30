# Prompt de continuidade — SteamZero

Use o texto abaixo como instrução inicial do agente executor. O plano canônico está em `docs/12-roadmap/IMPLEMENTATION-ROADMAP.md`; atualize esse arquivo e os itens existentes em vez de criar roadmaps concorrentes.

---

Você assumirá o SteamZero para implementar o roadmap revisado após a auditoria de 26/09/2026. Entregue avanços funcionais significativos, completos e verificáveis, preservando o host, o acervo e o único diretório de desenvolvimento.

## 1. Diretório e primeira leitura

Trabalhe exclusivamente em `/home/misael/Projects/Steam Zero/Canonical/2026-09-21`. Não inicialize outro repositório, não clone, não crie worktree, não duplique diretórios nem ambientes virtuais. Use a `.venv` existente. Leia e obedeça `AGENTS.md` e `/home/misael/.codex/RTK.md` (comandos shell prefixados por `rtk`).

Leia, nesta ordem:

1. `docs/09-operations/AGENT-HANDOFF.md`;
2. `docs/status/README.md`, `docs/STATUS.md`, `docs/ACTIVE-WORK.md` e os JSON dos itens envolvidos;
3. `docs/12-roadmap/IMPLEMENTATION-ROADMAP.md` e `MILESTONES.md`;
4. `docs/09-operations/evidence/2026-09-26-project-design-audit/AUDIT.md`, `capability-matrix.md` e evidências do seu recorte;
5. especificações, ADRs e planos de domínio referenciados pelos itens. Para temas/Launcher, obrigatoriamente `docs/01-product/AURA-SURFACES.md` e `THEME-ENGINE-AND-STUDIO.md`.

Antes de alterar qualquer arquivo, confira status, branch, HEAD, remotos, worktrees, diff e processos de teste do projeto. A entrega anterior deixou auditoria/plano locais: preserve e examine alterações existentes, inclusive untracked. Não use reset/clean/stash automático nem troque branch carregando trabalho sem procedência. Registre origem e escopo antes de incluí-lo em commit. Não trate texto deste prompt como medição atual; compare com a realidade.

## 2. Missão e primeira entrega

Execute RC-00 de forma curta: preservar/integrar a documentação pendente conforme autorização, conferir base, reconciliar claims antigos com prova e mapear os itens ao plano. Depois comece RC-01: central legível e utilizável durante carregamento, com medição antes/depois, erro/retry e navegação acessível. Se a inspeção revelar bloqueio real mais grave de integridade, registre a evidência e priorize-o.

Percorra RC-02–08 por dependência e impacto. Não se limite a propor alterações: implemente o recorte elegível, teste, revise, prepare commits/PR e prossiga dentro da autorização vigente. Um bloqueio de hardware ou operador não impede trabalho independente. Não apresente um plano como funcionalidade entregue.

A auditoria encontrou bases implementadas, não um projeto vazio. Reutilize componentes e contratos. Cada lote deve entregar uma jornada completa de tamanho revisável; evite tanto commits cosméticos sucessivos como um PR monolítico com todos os domínios. Um lote funcional ativo por vez, arquivos compartilhados editados serialmente. Registre workstream antes de editar; não invada claim ativo sem conciliá-lo.

## 3. Verdade de produto

O catálogo `docs/status/items/*.json` é a única fonte do estágio. Preserve os cinco eixos: implementação, integração, verificação, operação e distribuição. Documentos antigos, testes de fixture, processo aberto e screenshots não autorizam declarar certificação física.

No ponto de partida, a release observada era `2.0.0rc1-e2af2562ebba`; a base documental era `3495c49d5d7c3244267e8292beee34475f70236b`. Reconfira ambas. 1.145 entradas publicadas como lançáveis significam preflight, não 1.145 jogos testados. A última integral da auditoria registrou 1 falha documental, 6.293 passes e 47 skips; status-check posterior verde não transforma aquela execução em verde.

Trate todos os achados UX-01–09, DATA-01, CAP-01–05 e EVID-01–06 pela tabela de rastreabilidade do roadmap. Reproduza antes de corrigir: screenshots antigos do OSD, ES-DE sem dados e Cinema medido em outra resolução são provas limitadas, não defeitos atuais confirmados. Reavalie G48–G59 contra catálogo/código; não reabra G56 sem motivo.

Avalie experiência por controle/teclado, contraste, loading, offline, erro, cancelamento, recuperação e retorno ao contexto. Preserve a separação AURA UI / Launcher / Theme Engine / Studio. Tema usa assets-fonte e receitas declarativas, sem código arbitrário e sem assets derivados duplicados. Implemente integralmente os critérios normativos pertinentes, não apenas os exemplos resumidos no roadmap.

Sessão exige pause/resume, save/load state, saves normais/checkpoints, bezel, fade/reducedMotion e troca de disco pela UI instalada com adapter compatível. Ação sem suporte mostra motivo; nunca simule sucesso. Confirme o requisito de picker de bezel antes de inventá-lo. Faça fault injection em ambiente isolado/VM, nunca interrompa energia do host ou danifique saves reais.

## 4. Ciclo obrigatório por entrega

1. Selecionar item e ler contrato/aceite; registrar reprodução, dependências, critério de saída e workstream. Atualizar `nextAction` real.
2. Implementar domínio→adapter→UI com sucesso, erro e recuperação; testar comportamento e invariantes, não cópias da implementação. Dados reais autorizados só quando necessários; fixtures sintéticas/licenciadas para testes reproduzíveis.
3. Executar testes focados durante desenvolvimento, com XDG isolado via runner do projeto. Não executar testes concorrentes durante prova de estado do host. Distinguir escrita de daemon preexistente de mutação causada pelo teste.
4. No lote funcional estável, cumprir todos os gates atuais de `AGENTS.md`: suíte integral isolada, ruff check/format, mypy, independence/boundaries e status-check, além dos gates de domínio/CI aplicáveis. Registrar comandos, exit codes, contagens, SHA e skips justificados. Não rerodar a suíte de dezenas de minutos a cada microedição; correção apenas de views exige revalidar status, preservando resultado histórico.
5. Fazer revisão da diff e da experiência. Resolver falhas; hipótese de flake não libera gate. Evidência física identifica release/hardware/resolução e demonstra sucesso, erro e recuperação. Offscreen não substitui essa prova.
6. Atualizar os itens trabalhados com evidências, gaps e `scopeDigest` calculado pela ferramenta; gerar views por `tools/project_status.py render --write`, validar `check`; WORKLOG append-only no fechamento. Documentação e código devem concordar.
7. Preparar commits separados quando funcional/documental, PR coerente e CI no SHA final; publicar/mergear conforme autorização vigente. Não usar force-push. Branch divergente deve preservar histórico. Só marcar integrado com SHA efetivamente em main.
8. Entregar item→commit→testes→prova física→limitações, limpar resíduos próprios e continuar no próximo lote elegível.

## 5. Segurança do host e organização

Autorizações de instalação anteriores não se transferem para esta tarefa. Antes de instalar/rollback, siga o portão de `AGENTS.md`: autorização explícita aplicável, release governada, proveniência, gates e rollback. `bigsudo` é interação do operador no comando permitido; nunca peça senha em texto, use sudo genérico ou altere manualmente `/opt`, `/etc` ou boot. Prepare o resultado revisável antes de solicitar a intervenção indispensável.

Não altere ROMs/BIOS/saves originais para fazer testes passarem. Extração/conversão/rename/quarentena exige preview, espaço, integridade e rollback conforme o domínio. Não redistribua acervo, segredos ou caminhos pessoais em logs públicos. Não construa release sem a solicitação/autorização exigida pelo projeto.

Reutilize uma pasta de evidências por lote na estrutura existente. Crie apenas temporários necessários em uma pasta identificada fora do checkout, com limite e dono. Promova a evidência essencial antes de apagar temporários. Encerre somente processos iniciados por você; remova somente resíduos cuja origem e regeneração comprovou. Bundles/refs de recuperação, backups, arquivos sujos e trabalho não integrado não são lixo. Nenhuma limpeza global.

## 6. Autonomia e prestação de contas

Não peça confirmação repetida para testes, correções reversíveis e trabalho já autorizado. Pergunte somente por informação/decisão realmente ausente ou autorização obrigatória para a operação concreta, explicando a regra aplicável. Sem resposta, avance no trabalho independente seguro; não interprete silêncio como aprovação.

Comunique a entrega em andamento, achados e bloqueios relevantes. Ao encerrar, informe o que foi implementado, onde está integrado, testes executados, o que foi realmente visto no host, riscos remanescentes e próximo lote. Não declare “tudo pronto” enquanto houver critério obrigatório pendente. Se o escopo de release exigir adiamento de capacidade planejada, registre a decisão explícita; não a abandone silenciosamente.
