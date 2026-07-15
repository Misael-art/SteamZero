# USER-DATA-PRESERVATION — preservação de dados do usuário em migrações

## Classificação de dados (ordem de sacralidade)

1. **Saves/states** — insubstituíveis. 2. **Dumps próprios (ROMs/BIOS/keys)** — caros de reproduzir. 3. **Customizações** (configs, presets, layouts de controle) — trabalho do usuário. 4. **Mídia raspada** — re-obtenível. 5. **Componentes** — reinstaláveis.

## Regras invioláveis (aplicam-se a TODA migração/import/update)

1. Classe 1–2: **nunca movidas nem reescritas** por migração; adoção é por referência; reorganização física é operação separada com copy-verify-commit (original apagado só após verificação e confirmação — e mesmo assim vai a backup na janela de retenção).
2. Classe 3: qualquer sobrescrita passa por diff exibido + backup; "restaurar defaults" preserva o custom em backup restaurável.
3. Migração interrompida (energia/crash) nunca deixa dados em estado meio-movido: padrão copy→verify→switch→(GC depois), journalizado.
4. Import é idempotente: reexecutar detecta o já-adotado (por hash) e não duplica.
5. Toda migração produz relatório: encontrado/adotado/pulado/conflitos, exportável.
6. Conflito (dois candidatos para o mesmo slot — ex.: mesmo jogo em dois lugares): nunca escolher silenciosamente; registrar ambos e pedir decisão (mesma filosofia de J6).
7. "Dry-run de migração" (plan+preview) disponível sempre, inclusive por CLI para P2 auditar antes.
