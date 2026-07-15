# RECOVERY — runbooks de recuperação

Cada alerta crítico da UI referencia um runbook. Estrutura: sintoma → diagnóstico → recuperação assistida → recuperação manual (P2/suporte).

## R1. `rollback-failed` (FM-17)

Recurso congelado. Assistida: `steamzero recovery inspect <operationId>` mostra o diff backup×atual; `steamzero recovery restore <operationId> --entry N` restaura entradas individualmente (verificado). Manual: backup em `backups/<opId>/payload/` com manifesto legível — instruções de cópia manual documentadas no próprio manifesto (`README` gerado no diretório).

## R2. state.db corrompido

Daemon sobe em modo recovery: integrity_check falha ⇒ tenta backup mais recente do state (backup automático diário + pré-update) ⇒ se não houver, **reconstrução**: state é re-derivável por rescan (biblioteca, componentes, BIOS) + journal (operações) + timeline de saves (blobs têm manifestos próprios). Dados de usuário nunca dependem do state.db para existir.

## R3. Journal com intents abertos e recovery falhando

`steamzero recovery journal <opId>` lista ações intent-sem-done com undo previsto; execução ação a ação com confirmação; impasse ⇒ quarentena do recurso + bundle.

## R4. Staging/backups encheram o disco

GC assistido com preview (nunca automático além da política); prioridade de retenção explicada; `steamzero backup gc --plan`.

## R5. Plataforma não sobe após update

Rollback de plataforma (UPDATE-AND-ROLLBACK) via CLI; se CLI indisponível: Flatpak `flatpak update --commit=<anterior>` documentado no guia de usuário; state restaurável de backup pré-update.

## R6. Decky/QAM quebrado pós-update do Steam

FM-11: nenhuma recuperação necessária no núcleo; runbook = comunicar caminhos alternativos + aguardar Compat Matrix atualizada.

## R7. microSD com erros de I/O

Escritas suspensas (FM-07); assistida: relatório de integridade, cópia de resgate (read-only) dos dados legíveis para o SSD com verificação, jogo a jogo; nunca "reparar" o cartão automaticamente.

## Princípio

Recuperação nunca destrói evidência: antes de qualquer ação de recovery, o estado defeituoso é preservado (cópia/quarentena) para diagnóstico.
