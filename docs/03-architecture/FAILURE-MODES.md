# FAILURE-MODES — modos de falha e respostas planejadas

Protocolo universal (§5.3): `detect failure → stop safely → collect diagnostics → rollback → verify rollback → report result`.

| # | Falha | Detecção | Resposta | Estado final garantido |
|---|---|---|---|---|
| FM-01 | Rede cai durante download | curl/net layer erro ou stall (low-speed timeout) | job `blocked(network)`; staging parcial retido p/ resume com range request + re-hash | Nenhuma mutação fora do staging |
| FM-02 | Download corrompido | sha256 divergente do manifesto | descarta staging; retry N vezes; depois `failed` `E-SUPPLY-CHECKSUM` | idem |
| FM-03 | Disco cheio no meio do apply | preflight com margem + ENOSPC handler | stop → rollback → verify | Estado anterior restaurado |
| FM-04 | Crash/SIGKILL do daemon durante apply | journal WAL com intents pendentes na subida | recovery: undo de intents sem done (ou roll-forward pós-activate) | Journal consistente; sem órfãos |
| FM-05 | Queda de energia durante escrita de config | escrita atômica (tmp+fsync+rename) | arquivo antigo OU novo, nunca truncado | Config íntegra |
| FM-06 | microSD removido com jogo/dados nele | monitor de mounts por UUID | entidades → `unavailable(storage-missing)`; escritas bloqueadas; links NÃO reescritos | Nada apagado; restauração automática no retorno |
| FM-07 | Erro de I/O no microSD | erros de leitura/SMART-like heurísticas | relatório de integridade; jobs no volume pausados | Sem escrita em mídia suspeita |
| FM-08 | Emulador trava (não responde a fechar) | SessionManager timeout | `closing`→escalada: sinal semântico → SIGTERM → (usuário confirma) SIGKILL; saves do último flush intactos | Timeline de saves preservada |
| FM-09 | Suspensão no meio de job | inibidor systemd + pre-suspend hook | job pausa em ponto de segurança antes da suspensão (ou aborta etapa re-executável) | Resume correto pós-retomada |
| FM-10 | Atualização SteamOS muda paths/versões | Compat Matrix na subida + doctor | modo degradado explícito: capacidades incompatíveis desativadas com aviso, nunca "tentar mesmo assim" | Sem mutação sob incompatibilidade |
| FM-11 | Decky quebrado pós-update | QAM adapter healthcheck | QAM off; Game Mode UI/CLI/API seguem (P9) | Plataforma funcional |
| FM-12 | JSON/XML/INI de config inválido (corrompido ou editado) | parser estruturado + schema | backup automático do corrompido → oferta: restaurar último válido / defaults por seção | Nunca sobrescreve o corrompido sem backup |
| FM-13 | Symlink malicioso/loop em árvore de ROMs | core.fs: O_NOFOLLOW, realpath containment, limite de profundidade | item em quarentena lógica + `E-CONTENT-UNSAFE-PATH` | Sem leitura/escrita fora da raiz permitida |
| FM-14 | Zip bomb em import | safezip (limite de razão de expansão/entradas/profundidade — precedente `library/safezip.py`) | quarentena + erro | Extração confinada ao staging |
| FM-15 | Lock órfão (crash anterior) | lease expirada + dono morto (pid ausente) | lock quebrado com registro; operação dona vai a recovery | Sem deadlock permanente |
| FM-16 | Conflito de save local×nuvem | hash + vetor {dispositivo, mtime lógico} | ambos preservados; estado `conflicted`; decisão do usuário | Zero sobrescrita automática |
| FM-17 | Falha no rollback | verify do rollback compara com backup manifest | `rollback-failed`: congela recurso, problema crítico no dashboard, instruções de recuperação manual + support bundle | Nada mais toca o recurso automaticamente |
| FM-18 | Display sem imagem pós-dock | timeout de confirmação de modo | cadeia de fallback (perfil→sem HDR→sem VRR→menos Hz→menos res→tela interna) com confirmação "manter?" 15s estilo Windows | Sempre volta a ter imagem |
| FM-19 | Bateria crítica durante conversão longa | monitor de energia | pausa em ponto de segurança; retomada ao carregar | Sem estado intermediário |
| FM-20 | Processo privilegiado indisponível (helper não instalado) | detect na chamada | funcionalidade degrada com explicação e instrução de instalação; nunca fallback silencioso p/ sudo | Sem escalada improvisada |
| FM-21 | Provider Desktop ausente/crasha (KDE, Steam, InputPlumber, teclado) | capability probe, timeout ou verify | desativa só a capacidade; avança fallback; mantém controle físico e status | Núcleo/recuperação operantes |
| FM-22 | Dois controladores disputam input/display | fingerprint instável, capture falho ou conflito declarado | bloqueia apply com E-DESKTOP-OWNER-CONFLICT; card persistente oferece remediação allowlisted com plano/confirmação; falha parcial restaura owner anterior | Nenhum segundo remapeador iniciado; sem falha silenciosa |
| FM-23 | Crash durante troca de perfil Desktop | snapshot `desktop-recovery` permanece `applying` | próxima subida oferece/roda restore reverso; falha congela recurso | Último estado capturado ou recovery explícito |
| FM-24 | Todos os efeitos Desktop indisponíveis | nenhum DesktopEffectPort disponível | aplica apenas estado nativo como `degraded`; modo seguro não captura dispositivos | Acesso físico preservado |
| FM-25 | Flatpak muda entre plan/apply ou processo cai após deploy | snapshot do deployment + intent durável + revalidação | recusa stale sem efeito ou recovery restaura commit anterior | App data preservado; deployment anterior restaurado |
