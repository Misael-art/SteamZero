# USER-JOURNEYS — jornadas críticas

Formato: passos → estados do sistema → pontos de falha tratados.

## J1. Primeiro uso (P1, Game Mode)

1. Instala via Flatpak/instalador → 2. Abre no Game Mode → 3. Assistente: escolhe armazenamento (SSD/microSD, com UUID) → 4. Seleciona plataformas → 5. Plano exibido (o que será instalado, espaço, tempo) → 6. Confirma → 7. Jobs com progresso real → 8. Dashboard "pronto para jogar" com pendências (BIOS ausentes).
- Falhas tratadas: rede cai (job pausa, retomável); espaço insuficiente (bloqueia no plano, não no meio); microSD lento/removido (aviso, re-plan).

## J2. Importar dumps próprios (P1/P2)

1. Conecta pendrive → 2. "Importar conteúdo local" → 3. Scan read-only mostra o que foi reconhecido (hash, plataforma, região) e o que não foi → 4. Preview: para onde cada arquivo vai, o que é duplicata, o que fica em quarentena → 5. Confirma → 6. Cópia com checksum + verificação → 7. Relatório.
- Falhas: zip bomb/path traversal (rejeição com código de erro); arquivo incompleto (quarentena); pendrive removido no meio (job pausa, resume seguro; original intocado).

## J3. Suspender no meio do jogo (P1)

1. Aperta power → 2. Session Manager entra `pre-suspend`: flush de saves solicitado ao emulador, checkpoint criado, sync pausado, dispositivos registrados → 3. `suspended` → 4. Retomada: validação processo/input/áudio/display/microSD/saves → 5. Só a camada defeituosa é corrigida (ex.: re-pair Bluetooth) sem reiniciar o jogo.
- Falha extrema: emulador morto na retomada → estado `recovering`, oferta de restaurar último save-state/checkpoint.

## J4. Dock ↔ portátil (P1/P3)

1. Encaixa no dock → 2. Máquina de modo: `handheld → docked-tv` → 3. Aplica perfil (resolução, HDR/VRR, áudio, controle principal, TDP, UI scale) → 4. Falha de display dispara cadeia de fallback (perfil conhecido → sem HDR → sem VRR → menos Hz → menos resolução → tela interna).

## J5. Atualizar um emulador (P2)

1. `steamzero component update duckstation --plan` → 2. Plano JSON: versão atual→alvo, checksum, espaço, riscos → 3. `--apply --confirm <token>` → 4. Staging, verify (binário roda `--version`), activate atômico → 5. Smoke test → 6. Commit. Falha em qualquer etapa = rollback automático + relatório.
- "A atualização falhou. A versão anterior foi restaurada." (ERROR-UX)

## J6. Conflito de save (P1/P2)

1. Jogou no Deck offline e no desktop → 2. Sync detecta divergência → 3. **Nunca sobrescreve**: mantém ambos, mostra "Existem dois progressos diferentes deste jogo" com metadados (dispositivo, hora, tempo de jogo) → 4. Usuário escolhe; o preterido vira versão na linha do tempo (restaurável).

## J7. microSD desapareceu (P1)

1. Jogo instalado no microSD; cartão removido → 2. Estado do jogo vira `unavailable(storage-missing)` — nunca "deletado" → 3. Dashboard e página do jogo explicam; escritas bloqueadas; links não são "reparados" para o vazio → 4. Cartão volta (UUID confere) → estado restaurado sem ação do usuário.

## J8. Diagnóstico e suporte (P1→P2)

1. Algo falhou → 2. Erro com código + "exportar diagnóstico" → 3. Pacote de suporte gerado, **exibido para revisão** (dados anonimizados, sem keys/saves) → 4. Usuário exporta manualmente.

## J9. Migração de instalação EmuDeck/RetroDECK existente (P2)

Ver 10-migrations/EMUDECK-IMPORT.md e RETRODECK-IMPORT.md: scan read-only do ecossistema existente → relatório de compatibilidade → plano de adoção (links, não movimentação destrutiva) → originais preservados até commit explícito.
