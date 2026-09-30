# Handoff do agente — 26/09/2026

## Onde continuar

Checkout único: `/home/misael/Projects/Steam Zero/Canonical/2026-09-21`.
A conferência desta revisão encontrou somente esse worktree, na branch
`codex/project-design-audit-2026-09-26`, HEAD
`3495c49d5d7c3244267e8292beee34475f70236b`.
A auditoria e a revisão do roadmap são alterações locais; confira `git status`
antes de agir e preserve todo conteúdo pendente. Não criar outro diretório de
trabalho para contornar uma árvore suja.

A ordem executiva está exclusivamente em
[IMPLEMENTATION-ROADMAP](../12-roadmap/IMPLEMENTATION-ROADMAP.md).
O [prompt de continuidade](../../IMPLEMENTATION-PROMPT.md) contém o procedimento
de retomada, autonomia, gates e disciplina de diretórios. Leia também `AGENTS.md`,
`docs/status/README.md`, as views e os itens pertinentes antes de editar.
Este handoff não mantém uma segunda fila de tarefas.

## O que já aconteceu

- Reconciliação seletiva das sete frentes integrada via PR #237, merge
  `1ffafa648b3d4b0ac2691c11fd300b7e66d0c95e`; arquivos não promovidos preservados
  em snapshots/bundle. Centralização não autoriza apagar as cópias de recuperação.
- Release observada `2.0.0rc1-e2af2562ebba`, rollback registrado
  `2.0.0rc1-621a3389db32`. Instalação/UI verificadas; gameplay completo não
  certificado. Reconfira release e condições atuais antes de qualquer operação.
- [Auditoria](evidence/2026-09-26-project-design-audit/AUDIT.md): scan persistente,
  matriz de capacidades, telas, temas, Studio/Cinema e gestão de sessão.
  Contratos e capturas históricas têm limites explícitos. O relatório contém
  achados confirmados e lacunas de evidência; não promover todas a “bugs”.
- Suíte integral auditada: 1 falha de views desatualizadas, 6.293 aprovados,
  47 ignorados. Views/status focado foram corrigidos/validados; aquela integral
  permanece não verde. Testes focados de temas/sessão/persistência passaram;
  no grupo de 208 houve escrita concorrente do daemon externo e guard degradado.

## Primeira ação e limites

Preservar/conferir a entrega documental pendente, RC-00 curto, depois RC-01.
Claims ativos antigos devem ser reconciliados com Git, catálogo e dono; não
assumir que branch antiga significa código ausente ou trabalho abandonado.
A tabela de rastreabilidade do roadmap cobre todos os achados e define aceite
por lote. Os planos especializados continuam definindo contratos do domínio.

AURA Launcher já tem provas físicas históricas; Studio já tem canvas/árvore/
inspector visíveis. Alegações antigas de ausência total estão superadas, mas
isso não satisfaz o DoD completo nem certifica a release atual. Conteúdo
reconhecido/BIOS encontrada/preflight lançável não provam gameplay.

Nenhuma autorização histórica de host passa automaticamente ao próximo agente.
Seguir o portão vigente de `AGENTS.md`; não instalar para “atualizar o ambiente”
sem autorização aplicável. Testes isolados e desenvolvimento podem continuar.
Relatos de bloqueios e inventários de agosto/setembro anteriores são históricos;
reproduzir a condição atual antes de usá-los como bloqueio.
