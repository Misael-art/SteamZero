# OPERATIONAL-TRUST-GATES — caminho até uma release confiável

Nenhuma nova feature de UI/Game Mode pode ultrapassar estes gates. “Código verde” não
é sinônimo de “produto confiável”; cada nível registra também o ambiente onde a prova
foi executada.

| Gate | Estado em 2026-07-16 | Critério de saída |
|---|---|---|
| G0 — preservação local | **concluído** | checkout autoritativo no Btrfs interno, `git fsck` íntegro e cópia original do microSD preservada |
| G1 — proteção externa | **bloqueado por credencial/destino** | remoto privado, push de todos os refs, proteção de `main`, tags protegidas e backup realmente off-host restaurado em teste |
| G2 — baseline honesta | **em fechamento** | `ports.py` canônico/empacotado, versão `0.1.0a1`, relatório e ledger consistentes, commit limpo |
| G3 — CI real | **implementado, ainda não executado remotamente** | 3.11/3.12/3.14, clean wheel smoke e containers Ubuntu/Arch/Manjaro verdes no provedor |
| G4 — supply chain | **validado localmente; assinatura pendente** | locks/hashes, OSV, SBOM e proveniência verdes; assinatura verificável definida para o remoto privado |
| G5 — M10 real | **pendente** | VM descartável prova install/update/rollback de Dolphin e RetroArch; DuckStation usa fonte suportada e pinada |
| G6 — plano de controle | **pendente** | reconciliador user-scoped, IPC autenticado, polkit mínimo e lifecycle correto de subprocessos |
| G7 — hardware Deck | **pendente** | protocolo abaixo executado para KScreen/KWin, dock/hotplug, suspend, storage, TDP e rollback |
| G8 — UI/Game Mode/release | **congelado** | somente abre após G0–G7, incluindo testes QML, focus graph, acessibilidade, Flatpak, canais e assinatura |

## Protocolo mínimo para mutações no Deck

1. Executar primeiro em VM descartável e salvar logs/artefatos do mesmo commit.
2. Criar snapshot Btrfs nomeado e confirmar espaço, montagem e procedimento de restore.
3. Garantir console de recuperação independente da sessão gráfica: TTY local e SSH por
   uma segunda máquina, ambos testados antes da mutação.
4. Registrar baseline read-only: saídas KScreen, KWin, unidades systemd, mounts, bateria,
   TDP e processos owners.
5. Aplicar uma capacidade por vez com plano, confirmação, snapshot e deadline automático
   de rollback; nunca agrupar display, input, storage e TDP na primeira execução.
6. Exercitar dock→undock, hotplug, suspend→resume e queda do processo no meio do apply.
7. Confirmar estado observado, reiniciar a sessão e então reiniciar o host; divergência
   produz `stale`/`degraded`, nunca sucesso implícito.
8. Restaurar o snapshot em ensaio controlado e anexar a evidência ao relatório.

O host principal não é a primeira bancada destrutiva. Sem snapshot restaurável e console
secundário comprovado, o gate G7 permanece fechado.
