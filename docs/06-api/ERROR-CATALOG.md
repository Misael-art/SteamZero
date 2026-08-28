# ERROR-CATALOG — catálogo de erros com códigos estáveis

## Formato do código

`E-<ÁREA>-<NOME>` (estável para sempre; nunca reutilizado com outro significado; remoção = deprecado, não reciclado).

Todo erro carrega: `code, title (humano), what (o que aconteceu), impact, probableCause, autoAction (o que o sistema já fez), manualAction (o que o usuário pode fazer), operationId, detailsRef` (07-ui-ux/ERROR-UX.md rege a apresentação).

## Áreas (registro espelha `ERROR_CATALOG` em `src/steamzero/core/errors.py`)

### TX — transações
- `E-TX-CONFIRM-REQUIRED` plano exige confirmToken.
- `E-TX-STALE-PLAN` plano recusado: desatualizado, inválido (destino existente, symlink, duplicidade, ciclo) ou precondição não cumprida; o detalhe nomeia a condição (AC-TX-01).
- `E-TX-VERIFY-FAILED` pós-condição falhou; rollback automático executado.
- `E-TX-ROLLBACK-FAILED` rollback não restaurou o estado; recurso congelado (FM-17).
- `E-TX-LOCKED` recurso em uso por outra operação (inclui dono e idade do lock).
- `E-TX-CUSTODY-CROSS-FS` quarentena em outro filesystem; recusado sem tocar no alvo.

### SUPPLY — obtenção de artefatos
- `E-SUPPLY-NO-CHECKSUM` manifesto sem sha256 para artefato não-flatpak.
- `E-SUPPLY-CHECKSUM` hash divergente ("O download não confere com o esperado e foi descartado.").
- `E-SUPPLY-OFFLINE` operação requer rede e a tentativa de obtenção falhou; nada foi instalado.
- `E-SUPPLY-UPSTREAM-GONE` release/asset não existe mais.
- `E-SUPPLY-REMOTE-FAILED` operação remota interrompida; item retorna para a fila.

### STORAGE
- `E-STORAGE-SPACE` "São necessários mais X GB para concluir <operação>." (com cálculo de margem)
- `E-STORAGE-MISSING` "O cartão microSD usado por este jogo não foi encontrado." (UUID, último visto)
- `E-STORAGE-IO` erros de leitura/escrita no volume; escritas suspensas.
- `E-STORAGE-RO` filesystem somente leitura.

### CONTENT
- `E-CONTENT-UNSAFE-ARCHIVE` zip bomb/estrutura maliciosa; item em quarentena.
- `E-CONTENT-UNSAFE-PATH` traversal/symlink fora da raiz.
- `E-CONTENT-INCOMPLETE` conteúdo incompleto, corrompido ou divergente do registrado (dump, download ou backup).
- `E-CONTENT-BUSY` jogo em execução durante operação de preservação; operação bloqueada.
- `E-CONTENT-BIOS-MISSING` "Falta <arquivo> (<plataforma>) para <emulador>." + ação importar.
- `E-CONTENT-FW-MISSING` firmware exigido ausente; ação importar.
- `E-CONTENT-FW-INCOMPAT` "O firmware selecionado não é compatível com este emulador."
- `E-CONTENT-KEYS-MISSING` keys exigidas ausentes; ação importar.
- `E-CONTENT-KEYS-INCOMPAT` arquivo de keys fora do conjunto reconhecido.
- `E-CONTENT-LIMIT` mídia acima do limite de importação (32 MiB).
- `E-CONTENT-UNSUPPORTED` tipo de arquivo não reconhecido (JPEG/PNG/WebP).
- `E-CONTENT-POLICY` ação recusada pela política local-owned-dump-only.

### COMPONENT
- `E-COMPONENT-UPDATE-ROLLEDBACK` "A atualização falhou. A versão anterior foi restaurada."
- `E-COMPONENT-DEGRADED` verify encontrou drift (com diff).
- `E-COMPONENT-NO-LAUNCH` componente sadio sem execução própria (core Libretro).
- `E-COMPONENT-UNSUPPORTED-DISTRO` sem source compatível com a distro detectada.

### SAVES
- `E-SAVES-CONFLICT` "Existem dois progressos diferentes deste jogo." (nunca auto-resolve)
- `E-SAVES-FLUSH-TIMEOUT` emulador não confirmou flush antes da suspensão; checkpoint anterior usado.

### SESSION / MODE
- `E-SESSION-INTERRUPTED` launcher caiu antes de concluir; exige recuperação explícita.
- `E-SESSION-LAUNCH-FAILED` processo/runtime falhou antes de concluir o lançamento; o host permanece utilizável.
- `E-SESSION-ORPHANED` sessão constava ativa, mas o processo já não existe; encerrada como falha no registro pelo reaproveitador de sessões.
- `E-SESSION-RESUME-DEGRADED` camada X falhou na retomada; reparo aplicado/pendente.
- `E-MODE-DISPLAY-FALLBACK` fallback de display acionado (registrando em qual degrau parou).

### DESKTOP
- `E-DESKTOP-OWNER-CONFLICT` outro processo altera/captura o mesmo recurso; permanece observador.
- `E-DESKTOP-CONFLICT-RELEASE` stop/disable/verificação do owner externo falhou; permanece observador e restaura o estado anterior quando necessário.
- `E-DESKTOP-VERIFY` efeito não confirmou o perfil; snapshots aplicados são revertidos.
- `E-DESKTOP-RECOVERY` rollback de um ou mais efeitos falhou; novas mudanças são congeladas.
- `E-DESKTOP-OBSERVE` sonda de estado não respondeu; perfil ativo não identificado; nada foi alterado.

### HOST — ativação e convergência
- `E-HOST-RELEASE-MISMATCH` a release ativa difere da esperada; nenhum serviço é reiniciado.
- `E-HOST-DAEMON-PENDING` o daemon reiniciou, mas continua respondendo pela release anterior.
- `E-HOST-CONVERGENCE-TIMEOUT` o daemon não confirmou sua identidade no prazo de convergência.
- `E-HOST-RESTART-FAILED` as units gerenciadas não puderam ser reiniciadas.
- `E-HOST-CURRENT-UNREADABLE` o apontador da release ativa está ausente, quebrado ou inacessível.

### PRIV
- `E-PRIV-DENIED` ação fora da allowlist / polkit negado.
- `E-PRIV-HELPER-MISSING` helper não instalado (com instrução).
- `E-PRIV-PROTO-MISMATCH` versão de protocolo incompatível.

### API
- `E-API-SCHEMA` parâmetro inválido (campo apontado). Só para pedido malformado —
  pré-condição de estado que recusa a operação usa o código do domínio
  correspondente (ex.: `E-TX-CONFIRM-REQUIRED` para token inválido ou expirado).
- `E-API-UNKNOWN-ACTION` método fora da allowlist. Não reaproveite `E-API-SCHEMA`
  aqui: rota inexistente e campo inválido são falhas diferentes para o usuário.
- `E-API-CONTRACT` versão de contrato incompatível.
- `E-API-RESPONSE-TOO-LARGE` resposta acima do limite do transporte local.
- `E-API-GENERATION-MISMATCH` o serviço em background responde por versão diferente da instalada; reinicie o serviço.

### CLI / ESTADO / INTERNO
- `E-CLI-USAGE` comando invocado de forma inválida.
- `E-STATE-MIGRATION` migração do State Store não concluída; backup mantido para restauração.
- `E-STATE-INTEGRITY` dado persistido pelo SteamZero ausente, inválido ou corrompido; a operação que dependia dele foi recusada.
- `E-INTERNAL-UNEXPECTED` erro interno não previsto; pacote de suporte e relato.
- `E-CONVERT-TIMEOUT` conversão excedeu o tempo previsto; arquivo original intacto.
- `E-CONVERT-FAILED` conversão não produziu saída válida; arquivo original intacto.

### JOBS
- `E-JOBS-BLOCKED-GAMEPLAY` job proibido durante jogo ativo.
- `E-JOBS-BLOCKED-BATTERY` aguardando energia.

### NET
- `E-NET-INSECURE-URL` URL sem TLS ou com credencial embutida.
- `E-NET-HOST-DENIED` destino fora da allowlist declarada.
- `E-NET-REDIRECT-DENIED` redirect saiu do esquema/host permitido.
- `E-NET-TIMEOUT` origem não respondeu no prazo.
- `E-NET-OFFLINE` conexão indisponível; estado local preservado.
- `E-NET-HTTP` status HTTP de falha, com status apenas nos detalhes variáveis.
- `E-NET-CONTENT-LIMIT` corpo declarado ou recebido excedeu o teto.
- `E-NET-CANCELLED` cancelamento observado sem publicar download parcial.

### SCRAPE
- `E-SCRAPE-PROVIDER-UNREACHABLE` provedor não respondeu; fallback continua.
- `E-SCRAPE-RATE-LIMITED` limite de taxa do provedor; novo backoff automático.
- `E-SCRAPE-QUOTA-EXCEEDED` cota do período esgotada; provedor desligado até renovar.
- `E-SCRAPE-NOT-FOUND` nenhum candidato para o jogo/tipo de mídia.
- `E-SCRAPE-DOWNLOAD-FAILED` download de mídia interrompido ou corrompido; staging limpo.
- `E-SCRAPE-CORRUPT-MEDIA` magic bytes divergentes do formato esperado; arquivo descartado.
- `E-SCRAPE-CREDENTIAL-MISSING` provedor exige credencial não configurada.
- `E-SCRAPE-CREDENTIAL-REJECTED` credencial armazenada recusada pelo provedor.
- `E-SCRAPE-VAULT-UNAVAILABLE` Secret Service da sessão indisponível.
- `E-SCRAPE-CACHE-FULL` cache de mídia excedeu o limite; limpeza ou aumento do teto.
- `E-SCRAPE-HTTP-ERROR` provedor respondeu com erro HTTP inesperado; fallback continua.
- `E-SCRAPE-OFFLINE` conexão com o provedor indisponível; operações locais continuam.

### MOD (mods de Switch)
- `E-MOD-NOT-FOUND` mod inexistente no catálogo ou não instalado.
- `E-MOD-DOWNLOAD-FAILED` download interrompido ou corrompido; temporário limpo.
- `E-MOD-INSTALL-FAILED` instalação no diretório do emulador falhou.
- `E-MOD-SOURCE-UNREACHABLE` repositório de mods não respondeu.
- `E-MOD-BUILD-ID-MISSING` Build ID indisponível; busca cai para Title ID.
- `E-MOD-TITLE-ID-NOT-FOUND` jogo sem Title ID identificado; atualize a biblioteca.
- `E-MOD-EMULATOR-NOT-FOUND` emulador alvo indisponível no sistema.
- `E-MOD-CATALOG-STALE` catálogo local desatualizado (> 24 h); sincronize.

### ENHANCEMENT (melhorias por jogo)
- `E-ENHANCEMENT-DENIED` melhoria recusada pelo invariante anticheat (categoria de gameplay, desconhecida ou sem proveniência).

### CHEAT (cheats de Switch)
- `E-CHEAT-NOT-FOUND` cheat inexistente no catálogo ou não instalado.
- `E-CHEAT-DOWNLOAD-FAILED` download interrompido ou corrompido; temporário limpo.
- `E-CHEAT-INSTALL-FAILED` instalação no diretório do emulador falhou.
- `E-CHEAT-SOURCE-UNREACHABLE` repositório de cheats não respondeu.
- `E-CHEAT-BUILD-ID-MISSING` Build ID indisponível; busca cai para Title ID.
- `E-CHEAT-BUILD-ID-MISMATCH` Build ID (do arquivo ou do catálogo) não é um hexadecimal instalável.
- `E-CHEAT-EMULATOR-NOT-FOUND` emulador alvo indisponível no sistema.
- `E-CHEAT-CATALOG-STALE` catálogo local desatualizado (> 24 h); sincronize.
- `E-CHEAT-INVALID-CODES` códigos fora do formato Atmosphere/EdiZon (reservado; a emissão real usa `E-CHEAT-CODE-INVALID`).
- `E-CHEAT-CODE-INVALID` arquivo/entrada de catálogo de códigos não aceito (irregular, > 4 MiB, ilegível ou sem códigos válidos).

### THEME (framework declarativo de temas)
- `E-THEME-MANIFEST` manifesto ausente, malformado ou fora do schema.
- `E-THEME-INCOMPATIBLE` versão da API do tema incompatível com a instalação.
- `E-THEME-UNSAFE` pacote com conteúdo ou caminho proibido.
- `E-THEME-LIMIT` limites de tamanho, quantidade ou profundidade excedidos.
- `E-THEME-NOT-FOUND` tema inexistente no catálogo ou removido manualmente.
- `E-THEME-ACTIVE` tema ativo não pode ser removido sem selecionar outro antes.
- `E-THEME-DOWNLOAD-FAILED` falha ao baixar ou extrair o pacote do tema.
- `E-THEME-CATALOG-FAILED` catálogo remoto inacessível ou inválido.
- `E-THEME-MARKETPLACE-DISABLED` marketplace remoto desligado de fábrica; exige configuração explícita.

### CAST (compartilhamento de tela, ADR-0022)
- `E-CAST-NO-RECEIVER` nenhum receptor comprovou o modo pedido; a mensagem indica
  ligar a TV na mesma rede ou usar espelhamento — nunca "erro desconhecido".
- `E-CAST-RECEIVER-INCOMPATIBLE` capacidade observada não cobre modo, resolução ou
  codec. Emitido também quando falta interseção de codec com o piso H.264/Opus.
- `E-CAST-ENGINE-MISSING` a via depende de um motor de transmissão ausente; a ação é
  instalar pelo próprio produto, de forma reversível.
- `E-CAST-PAIRING-REJECTED` receptor recusou o pareamento ou o código expirou; nenhum
  dispositivo é salvo como confiável.
- `E-CAST-CONSENT-REQUIRED` sem autorização do portal, ou escopo concedido não cobre o
  modo (janela não autoriza espelhar a tela inteira). Também é o código da revogação
  de consentimento durante a sessão.
- `E-CAST-PROTECTED-CONTENT` conteúdo protegido: o envio pausa e a sessão continua;
  nenhum contorno de HDCP/DRM é tentado.
- `E-CAST-LINK-LOST` enlace perdido após o backoff completo (0, 1, 2, 4, 8 s).
- `E-CAST-STATE-INVALID` transição não declarada na máquina de sessão; o pedido é
  recusado e o estado anterior permanece.
- `E-CAST-UNAVAILABLE` orquestrador de compartilhamento não configurado na bridge Desktop.
- `E-CAST-UNKNOWN-PROTOCOL` protocolo de transmissão pedido não reconhecido.

## Governança

Novo código exige: entrada neste catálogo + textos pt-BR/en + teste que o dispara. CI falha se código emitido não consta no catálogo — a promessa é executada por `tests/unit/test_errors.py::test_every_code_literal_in_src_is_registered`, que varre os literais `E-*` de `src/` contra o registro; emitido sem registro faz `SteamZeroError` recusar a construção e o usuário ver erro interno em vez da causa. Auditoria de verdade dos textos (causa real? ação resolve?): 2026-08-27, corrige `E-TX-STALE-PLAN`, `E-STATE-INTEGRITY`, `E-CONTENT-INCOMPLETE`, `E-SESSION-LAUNCH-FAILED`, `E-SUPPLY-OFFLINE` e registra 4 códigos emitidos sem registro.
