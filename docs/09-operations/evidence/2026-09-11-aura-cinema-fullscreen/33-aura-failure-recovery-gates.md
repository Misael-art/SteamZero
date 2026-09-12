# Gate — erro e recuperação do AURA Launcher

Data: 2026-09-12  
Commit funcional: `861a43e`  
Execução isolada: `steamzero-aura-gates-861a43e.service`  
Resultado da unidade: `success`, exit `0`

- pytest: **5.958 passed, 47 skipped**, 36 min 07 s;
- JUnit: `33-aura-failure-recovery-gates.xml`, SHA-256
  `9d3358d83568bc7ca55b83ef4c32a55e03743c45ddeca2b4966b6c0f04da0a8b`;
- Ruff check: verde;
- Ruff format: 602 arquivos já formatados;
- mypy: 271 arquivos sem erros;
- independência: verde;
- fronteiras: 0 violações;
- status-check: verde.

O runner detectou escrita no state real durante a janela, atribuída aos donos
externos que já estavam ativos antes do teste: daemon e Launcher da release
instalada `2.0.0rc1-47511fbe3067`. A suíte não foi marcada como autora. O log
bruto não foi copiado porque a inspeção de processos do aviso continha argv
sensível; o JUnit foi verificado e não contém `--steamzero-token`.
