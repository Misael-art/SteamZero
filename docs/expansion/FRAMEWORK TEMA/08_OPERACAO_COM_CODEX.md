# 8. Operação segura por agente de IA

## 8.1 Preflight obrigatório

1. Ler `AGENTS.md`, `/home/misael/.codex/RTK.md`, ADR-0002, ADR-0019, documentos de
   acessibilidade, navegação e segurança.
2. Confirmar branch própria `codex/*` baseada no tip indicado pelo operador.
3. Confirmar os preflights de base atualizada definidos em `AGENTS.md`.
4. Rodar `git status --short`, listar worktrees e preservar mudanças alheias.
5. Inventariar os valores temáveis reais no QML e os contratos da bridge.
6. Consultar a memória do projeto antes de propor alteração arquitetural.

## 8.2 Regras durante a implementação

- Todo comando de shell começa por `rtk`.
- Editar arquivos com `apply_patch`.
- Não instalar no host, não usar `sudo`/`bigsudo` e não gerar release.
- Não abrir `.env` nem incluir segredos, wheelhouse ou fixtures de outra frente.
- Não adicionar dependência sem ADR e justificativa.
- Não aceitar código executável em pacote de tema.
- Não enfraquecer teste, cobertura, independência ou fronteira.
- Não alterar `docs/WORKLOG.md` até o fim; apenas acrescentar a sessão.
- Revalidar arquivo compartilhado imediatamente antes de editá-lo.

## 8.3 Ciclo por item

Para cada `WI-Tn`:

1. registrar plano curto e arquivos;
2. escrever primeiro o teste de contrato/risco;
3. implementar o menor corte completo;
4. executar testes focados;
5. executar os quatro gates;
6. revisar `git diff --check` e o diff completo;
7. criar um commit único e descritivo;
8. só então iniciar o item seguinte.

## 8.4 Gates

```bash
rtk .venv/bin/pytest tests -q
rtk .venv/bin/ruff check src tools tests
rtk .venv/bin/mypy src
rtk make independence boundaries
```

UI também exige `qmllint` quando disponível e os harnesses offscreen relevantes. Ausência
de runtime Qt deve resultar em skip explícito, nunca em aprovação física.

## 8.5 Condições de parada

O agente deve parar e relatar antes de continuar se:

- a branch não descender da base indicada;
- um arquivo compartilhado mudou por outra frente;
- o plano exigir nova dependência, migração de banco ou código de terceiros;
- o tema padrão não reproduzir o visual existente;
- algum gate falhar por mudança da tarefa;
- houver dúvida de ownership em instalação/remoção;
- a única forma de avançar for relaxar segurança ou teste.

## 8.6 Relatório final

Tabela obrigatória:

| Item | Commit | Testes focados | Quatro gates |
|---|---|---|---|

Depois informar:

- arquivos e contratos criados;
- riscos e itens fora de escopo;
- ações de host executadas (esperado: nenhuma);
- validações físicas pendentes;
- branch e push realizados, sem force-push.
