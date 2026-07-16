# ACCEPTANCE-CRITERIA — critérios de aceitação por área

Formato Given/When/Then. Cada critério vira caso de teste em 08-testing/TEST-MATRIX.md.

## Transações (aplica-se a TODA operação mutável)

- AC-TX-01: Dado um plano gerado, quando qualquer arquivo-alvo muda entre plan e apply (hash divergente), então o apply é recusado com `E-TX-STALE-PLAN` e nenhuma mutação ocorre.
- AC-TX-02: Dado um apply em andamento, quando o processo é morto (SIGKILL) em qualquer ponto, então após reinício `verify` reporta o estado real e `rollback` restaura o estado inicial byte-idêntico (exceto mtimes), sem temporários órfãos.
- AC-TX-03: Dado `--dry-run`, então zero syscalls de escrita fora do diretório de staging/state (verificado com strace no CI).
- AC-TX-04: Todo apply exige `confirmToken` emitido pelo plano correspondente.

## Instalação de componentes

- AC-IN-01: Download sem checksum previsto no manifesto ⇒ falha `E-SUPPLY-NO-CHECKSUM` (não é warning).
- AC-IN-02: Instalar 2× o mesmo componente ⇒ segunda execução termina `no-op` com estado idêntico (idempotência).
- AC-IN-03: Falha de verify pós-instalação ⇒ rollback automático; componente volta ao estado anterior e o erro diz isso ("A atualização falhou. A versão anterior foi restaurada.").

## Biblioteca

- AC-LB-01: Scan nunca escreve fora do state store (read-only garantido).
- AC-LB-02: Conversão de ROM mantém o original até verify OK + commit; espaço é checado com margem antes do início.
- AC-LB-03: Arquivo com path traversal/zip bomb no import ⇒ quarentena + `E-CONTENT-UNSAFE-ARCHIVE`, nunca extração parcial fora do staging.

## BIOS/keys

- AC-BI-01: Nenhum hash/keyname de conteúdo protegido aparece em logs de nível < DEBUG-local; keys nunca aparecem em nenhum nível.
- AC-BI-02: BIOS ausente é reportada com plataforma+emulador afetado e ação "importar arquivo local" — nunca com link de download.

## Saves

- AC-SV-01: Conflito de save divergente nunca resolve sozinho: ambos preservados + UI de decisão (J6).
- AC-SV-02: Suspensão dispara checkpoint; queda de energia simulada após retomada não perde mais que o intervalo desde o último flush.
- AC-SV-03: Restauração por linha do tempo recupera qualquer versão retida byte-idêntica (checksum).

## Sessão/modos Deck

- AC-SD-01: Transição handheld↔docked aplica perfil em ≤5s sem reiniciar o jogo; falha de display percorre a cadeia de fallback até imagem válida.
- AC-SD-02: Remoção de microSD com jogo instalado nele ⇒ estado `unavailable`, zero escrita no mountpoint fantasma, restauração automática ao reinserir (UUID).

## Handheld Desktop

- AC-HD-01: Em instalação limpa sem PhaseZero, KDE, Steam, InputPlumber ou Qt, `desktop
  status|plan` e o modo seguro funcionam; build/test/runtime não acessam estado legado.
- AC-HD-02: Tela externa ou dock físico estável seleciona dock; teclado/mouse isolados
  não trocam o perfil; mudança do contexto invalida plano pendente.
- AC-HD-03: Todo apply captura snapshots antes do primeiro efeito; verify falho reverte
  em ordem inversa e crash deixa recovery persistente.
- AC-HD-04: Conflito de ownership bloqueia apply antes de chamar qualquer efeito; no
  máximo um provider é elegível, e InputPlumber exige validação explícita no hardware.
- AC-HD-05: UI portátil tem alvos ≥48 px, nomes acessíveis, grafo de foco e layout de uma
  coluna na largura lógica do Deck.
- AC-HD-06: conflito conhecido exibe card persistente com causa e impacto; a UI oferece
  plano revisável para `stop` + `disable` no escopo real da unidade, exige confirmação e
  restaura o estado anterior se a desativação falhar parcialmente.

## Offline

- AC-OF-01: Com rede desabilitada: iniciar jogo, carregar save, abrir biblioteca, usar BIOS local, rodar doctor — tudo funciona; operações remotas ficam `queued` e retomam com rede.

## UI/controle

- AC-UI-01: Toda tela é alcançável e operável apenas com gamepad (A confirma, B volta, shoulders trocam abas); teste automatizado de focus graph sem becos.
- AC-UI-02: Todo erro exibido tem código estável, impacto e ação; detalhes técnicos são opt-in.
- AC-UI-03: Progresso exibido deriva de medição real (bytes/itens/etapas); proibido progresso sintético.

## Privilégio

- AC-PR-01: Helper privilegiado rejeita qualquer ação fora da allowlist com `E-PRIV-DENIED`; fuzzing de parâmetros não produz execução arbitrária.
- AC-PR-02: Nenhum fluxo comum (instalar emulador Flatpak user, importar ROMs, saves) requer root.
