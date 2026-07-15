# GLOSSARY — glossário

| Termo | Definição no produto |
|---|---|
| Adapter | Módulo (manifesto + engine) que integra emulador/frontend/sistema, com capacidades declaradas |
| Ação semântica | Comando universal de jogo (ex.: "salvar estado") mapeado por adapter ao mecanismo real |
| BIOS-db | Banco de hashes/metadados de BIOS conhecidas (sem conteúdo) |
| Canal | Trilha de release (stable/beta/dev) com lockfile próprio |
| Checkpoint | Snapshot leve de save criado automaticamente (ex.: pré-suspensão) na timeline |
| Compat Matrix | Registro de combinações testadas {SteamOS, Steam Client, Decky, componentes, plataforma} |
| Componente | Software gerido (emulador, frontend, ferramenta) |
| confirmToken | Token single-use emitido pelo plan, exigido no apply (herdado do PhaseZero library pipeline) |
| Doctor | Diagnóstico read-only em camadas com checks codificados |
| Drift | Divergência entre estado observado (verify) e o esperado/gerido |
| Dupla-gestão | Mesmo dado gerido pelo Unified e por ferramenta original (EmuDeck/RetroDECK) — gera drift |
| Envelope v2 | Formato JSON padrão de saída CLI/API |
| G-FULL/G-STATE/G-TIMELINE | Classes de garantia de rollback (ROLLBACK-GUARANTEES) |
| Journal | Registro WAL por operação (intent→done) que permite recovery |
| Lease | Lock com expiração e dono verificável |
| Lockfile de componentes | Conjunto {versão+hash} de componentes testados com uma release |
| local-owned-dump-only | Política: só conteúdo que o usuário possui e fornece localmente |
| Operação | Execução de um plano transacional (operationId liga journal, backup, logs, job) |
| Ponto de segurança | Momento em que um job pode pausar/cancelar sem estado intermediário |
| Quarentena | Área para conteúdo suspeito/deslocado, sempre restaurável, nunca deletado automaticamente |
| Saga | Operação composta com compensação por sub-operação |
| Session Manager | Máquina de estados da sessão de jogo (launching…failed) |
| Staging | Área de preparação no mesmo filesystem do destino, descartável |
| State Store | SQLite com o estado observado das entidades |
| Timeline (de saves) | Histórico append-only de versões de save por jogo |
| Verify | Checagem objetiva de pós-condições (hash/versão/parse) — única fonte do status "ok" |
