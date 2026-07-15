# PRODUCT-PRINCIPLES — princípios não negociáveis

P1. **Reversibilidade antes de funcionalidade.** Nenhuma feature entra sem caminho de rollback testado (ver 08-testing/ROLLBACK-TESTS.md). Pipeline obrigatório: scan→plan→preview→backup→stage→apply→verify→activate→test→commit.

P2. **Menor privilégio.** Operações privilegiadas passam por um helper com allowlist pequena e parâmetros validados (03-architecture/PRIVILEGE-BOUNDARIES.md). Nunca `sudo` em bloco inteiro.

P3. **local-owned-dump-only.** O produto nunca procura, baixa, sugere ou contorna conteúdo protegido (04-security/CONTENT-POLICY.md).

P4. **UI não executa shell.** A UI fala com o serviço local por contrato tipado; o serviço expõe apenas ações da allowlist com schemas de parâmetros. Sem `eval`, sem nomes de função arbitrários.

P5. **Idempotência.** Executar duas vezes = mesmo estado final. Operações detectam estado atual antes de agir (padrão `detect → plan → apply-if-needed`).

P6. **Estados explícitos.** Tudo que importa (componente, job, save, BIOS, sessão, modo de dock) tem máquina de estados documentada e persistida no State Store.

P7. **Erro é interface.** Todo erro tem código estável, título humano, impacto, causa provável e ação recomendada (06-api/ERROR-CATALOG.md, 07-ui-ux/ERROR-UX.md). Nunca vazar stack trace cru para o usuário do Game Mode.

P8. **Offline é cidadão de primeira classe.** Nenhuma indisponibilidade de rede impede jogar, salvar, restaurar ou diagnosticar localmente. Operações remotas enfileiram.

P9. **Núcleo independente de UI e de Decky.** Game Mode UI, Desktop Mode UI, QAM e CLI são consumidores do mesmo serviço; a queda de qualquer um deles não derruba os demais.

P10. **Evidência antes de afirmação.** Status "instalado/válido/sincronizado" só é exibido se foi verificado (hash, versão, path real) — nunca inferido de "o instalador terminou sem erro".

P11. **Sem barra de progresso falsa.** Progresso reportado = progresso medido (bytes, itens, etapas). Se não é mensurável, mostrar etapa + spinner honesto.

P12. **Dados do usuário são sagrados.** Saves, ROMs, BIOS e mídias nunca são sobrescritos sem plano, preview, backup e confirmação. Conflito de save divergente mantém ambas as versões por padrão.
