# DATA-FLOW — fluxos de dados canônicos

## DF-1: Instalar/atualizar componente (ex.: DuckStation)

```
UI/CLI ── action:"component.update" {componentId} ──► API Server
  API valida schema + allowlist ──► Job Manager (job criado, queued)
  Job ──► Domain.Lifecycle:
    1. adapter.detect()            → versão atual, integridade
    2. manifesto (pinned version + sha256 + licença)  ← Compat Matrix
    3. plan (diff atual→alvo, espaço, riscos)         → State Store
    4. [espera confirmToken se poilcy=confirm]
    5. core.net.fetch → staging/  (checksum obrigatório)
    6. backup do estado atual     → backups/
    7. stage: descompacta/prepara em staging/
    8. verify: binário executa --version, sanidade de config
    9. activate: troca atômica (symlink flip / mv)
   10. test: smoke test declarado no manifesto
   11. commit: journal fechado, backup retido por política
  Eventos de progresso ──► Event Bus ──► UI (etapa, bytes, itens)
  Falha em 5–10 ⇒ rollback automático ⇒ verify do rollback ⇒ relatório
```

## DF-2: Import de dumps do usuário

```
storage adapter detecta mídia → scan read-only (hash BLAKE2b + assinaturas de formato)
→ classificação (plataforma/região/disco N de M) → plan {destino, duplicatas, quarentena}
→ preview na UI → confirm → cópia com verificação → registro no State Store
→ mídia original intocada (import é sempre cópia, nunca move por padrão)
Arquivos ilegíveis/suspeitos (zip bomb, traversal) → quarantine/ + evento
```

## DF-3: Save flow com suspensão

```
SessionManager(running) ─ udev/systemd-inhibit sinal pre-suspend ─►
  emulador.flush_save() (ação semântica se suportada) → checkpoint incremental
  → sync pausado → snapshot de dispositivos/display/áudio/controles → suspended
resume ─► validações camada a camada → só a camada quebrada é reparada
  → saves comparados (hash) → divergência ⇒ timeline entry, nunca overwrite
```

## DF-4: Sync com nuvem (offline-first)

```
Saves.timeline → fila de sync (State Store) → rede disponível?
  não ⇒ pending (visível no dashboard)  · sim ⇒ upload com hash
conflito remoto≠local ⇒ baixa remoto para timeline como versão paralela
  ⇒ estado "conflicted" ⇒ decisão do usuário (J6) — ambos preservados
```

## DF-5: Telemetria de erro → suporte

```
Erro (código estável) → log estruturado (sem segredos, paths anonimizáveis)
→ usuário aciona "exportar diagnóstico" → bundle gerado em staging
→ UI mostra conteúdo integral → usuário confirma → arquivo salvo onde ele escolher
(nenhum envio automático — N7)
```

## Classificação de dados (quem pode ver o quê)

| Dado | Em logs | No support bundle | Na API p/ UI |
|---|---|---|---|
| Keys/firmware de console | nunca | nunca | só status presente/ausente + hash truncado |
| Conteúdo de saves | nunca | nunca | metadados (jogo, hora, tamanho, hash) |
| Paths de ROMs | anonimizáveis (`$ROMS/...`) | anonimizados | completos (usuário local) |
| Tokens cloud | nunca (Secret type) | nunca | nunca (write-only) |
| Hardware/versões | sim | sim | sim |
