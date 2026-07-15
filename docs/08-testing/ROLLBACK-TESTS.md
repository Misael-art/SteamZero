# ROLLBACK-TESTS — testes de rollback (critério §13.6)

## Protocolo universal (todo RT executa)

1. **Snapshot A** do estado inicial (árvore de arquivos com hashes + dump lógico do State Store).
2. Executar a operação até o ponto de injeção.
3. **Injetar falha** (da tabela FI correspondente) — inclusive SIGKILL.
4. Rollback (automático ou `steamzero … rollback`).
5. **Snapshot B** e comparação com A.
6. Verificações de aprovação (todas obrigatórias):
   - estado restaurado (hashes idênticos; diferenças permitidas listadas explicitamente: logs, journal, mtimes);
   - dados do usuário preservados (fixtures de saves/ROMs intactas byte a byte);
   - **zero arquivos temporários abandonados** (varredura de staging/tmp);
   - journal consistente (nenhum intent aberto);
   - erro final compreensível (código do catálogo + mensagem do i18n).
7. **Idempotência do rollback** (RB-3): repetir rollback → mesmo resultado.
8. Relatório por caso (artefato de CI).

## Casos RT (referenciados na TEST-MATRIX)

RT-01 instalar componente (falha no verify) · RT-02 atualizar (falha no activate; falha no smoke test) · RT-03 desinstalar (falha no meio da remoção) · RT-04 reparar · RT-05 escrita de config (kill entre tmp e rename; restauração de backup adulterado deve FALHAR — T-09) · RT-06 conversão ROM (ENOSPC no meio; timeout; original intacto) · RT-07 import (fonte nunca alterada) · RT-08 links de BIOS (link quebrado no meio) · RT-09 restauração de save da timeline (restauração falha ⇒ save atual intacto) · RT-10 sync (upload interrompido ⇒ fila consistente) · RT-11 mídia (canonicalização revertida; órfãos de volta da quarentena) · RT-12 perfis de desempenho (G-STATE: valores anteriores reaplicados) · RT-13 shortcuts.vdf (arquivo restaurado byte-idêntico) · RT-14 update da plataforma (migração de state.db falha ⇒ backup restaurado; versão anterior operante).

## Gate

Nenhuma operação mutável entra em release sem seus RTs verdes, incluindo a variante SIGKILL de FI-04 em cada etapa do pipeline.
