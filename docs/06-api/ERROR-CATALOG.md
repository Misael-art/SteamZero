# ERROR-CATALOG — catálogo de erros com códigos estáveis

## Formato do código

`E-<ÁREA>-<NOME>` (estável para sempre; nunca reutilizado com outro significado; remoção = deprecado, não reciclado).

Todo erro carrega: `code, title (humano), what (o que aconteceu), impact, probableCause, autoAction (o que o sistema já fez), manualAction (o que o usuário pode fazer), operationId, detailsRef` (07-ui-ux/ERROR-UX.md rege a apresentação).

## Áreas e exemplos normativos (catálogo inicial; cresce por PR com revisão)

### TX — transações
- `E-TX-CONFIRM-REQUIRED` plano exige confirmToken.
- `E-TX-STALE-PLAN` precondições mudaram entre plan e apply (AC-TX-01).
- `E-TX-VERIFY-FAILED` pós-condição falhou; rollback automático executado.
- `E-TX-ROLLBACK-FAILED` rollback não restaurou o estado; recurso congelado (FM-17).
- `E-TX-LOCKED` recurso em uso por outra operação (inclui dono e idade do lock).

### SUPPLY — obtenção de artefatos
- `E-SUPPLY-NO-CHECKSUM` manifesto sem sha256 para artefato não-flatpak.
- `E-SUPPLY-CHECKSUM` hash divergente ("O download não confere com o esperado e foi descartado.").
- `E-SUPPLY-OFFLINE` operação requer rede; enfileirada (status blocked, não failure).
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
- `E-CONTENT-INCOMPLETE` dump incompleto/corrompido (hash conhecido divergente).
- `E-CONTENT-BIOS-MISSING` "Falta <arquivo> (<plataforma>) para <emulador>." + ação importar.
- `E-CONTENT-FW-INCOMPAT` "O firmware selecionado não é compatível com este emulador."
- `E-CONTENT-POLICY` ação recusada pela política local-owned-dump-only.

### COMPONENT
- `E-COMPONENT-UPDATE-ROLLEDBACK` "A atualização falhou. A versão anterior foi restaurada."
- `E-COMPONENT-DEGRADED` verify encontrou drift (com diff).
- `E-COMPONENT-UNSUPPORTED-DISTRO` sem source compatível com a distro detectada.

### SAVES
- `E-SAVES-CONFLICT` "Existem dois progressos diferentes deste jogo." (nunca auto-resolve)
- `E-SAVES-FLUSH-TIMEOUT` emulador não confirmou flush antes da suspensão; checkpoint anterior usado.

### SESSION / MODE
- `E-SESSION-INTERRUPTED` launcher caiu antes de concluir; exige recuperação explícita.
- `E-SESSION-LAUNCH-FAILED` processo/runtime falhou antes de concluir o lançamento.
- `E-SESSION-RESUME-DEGRADED` camada X falhou na retomada; reparo aplicado/pendente.
- `E-MODE-DISPLAY-FALLBACK` fallback de display acionado (registrando em qual degrau parou).

### DESKTOP
- `E-DESKTOP-OWNER-CONFLICT` outro processo altera/captura o mesmo recurso; permanece observador.
- `E-DESKTOP-CONFLICT-RELEASE` stop/disable/verificação do owner externo falhou; permanece observador e restaura o estado anterior quando necessário.
- `E-DESKTOP-VERIFY` efeito não confirmou o perfil; snapshots aplicados são revertidos.
- `E-DESKTOP-RECOVERY` rollback de um ou mais efeitos falhou; novas mudanças são congeladas.

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
- `E-SCRAPE-HTTP-ERROR` provedor respondeu com erro HTTP inesperado; fallback continua.
- `E-SCRAPE-OFFLINE` conexão com o provedor indisponível; operações locais continuam.

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

## Governança

Novo código exige: entrada neste catálogo + textos pt-BR/en + teste que o dispara. CI falha se código emitido não consta no catálogo.
