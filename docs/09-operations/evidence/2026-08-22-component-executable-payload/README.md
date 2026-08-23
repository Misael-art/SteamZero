# Payload engine commitado precisa ser executável

Data: 2026-08-22  
Branch: `codex/physical-functional-closure`  
Base do incremento: `5b9b4d1`

## Defeito reproduzido no host real

O deployment do Citron no host terminou com payload `0o600` (não executável)
em `2026-04-27-0237a9b88`. O `ctime` do arquivo prova que o último evento de
metadado foi a própria escrita do deploy (17/08 09:44:33): o `set_mode(0o700)`
do smoke nunca tocou o arquivo final. A reconstrução da linha do tempo aponta
para um replay de recovery, que re-copia o artefato pelo caminho da transação
sem passar pelo smoke do apply — quem aplica o bit de execução.

Consequências observadas no host, antes da correção, com o código da branch:

- `status` reportava `installed` com checksum íntegro;
- `verify` atestava `verified=true` e `repairable=false` — falso verde;
- `launch` morria com `PermissionError` cru de `execve`, sem erro estruturado.

Nenhum outro payload engine do host está nessa condição: duckstation, eden e
ryubing estão `0o700`.

## Reprodução vermelha automatizada

`TestExecutablePayloadInvariant` em `tests/integration/test_component_lifecycle.py`:

1. payload íntegro sem bit de execução ⇒ `status=degraded` com motivo dizível,
   `verify.verified=false`, `repairable=true`;
2. `launch` recusa com `E-COMPONENT-DEGRADED` estruturado, não `PermissionError`;
3. `plan(repair)` + `apply` restaura o bit de execução e termina `installed`.

Os três testes nasceram vermelhos no código anterior (`installed` onde o
contrato exige `degraded`) e ficaram verdes com a correção.

## Causa raiz e correção

Três lados do mesmo contrato:

- **Observação**: `engine.status()` validava apenas checksum. Payload sem bit
  de execução é um deployment que o `launch` não consegue iniciar — degradação
  com causa dizível, não um `installed` que o verify atestaria por engano.
- **Aplicação**: `verify_component` consultava `status` antes de aplicar o bit
  de execução, e resolvia o caminho por `payload_path`, que recusa estado não
  `installed`. Instalação engine nova falharia no próprio smoke por ordenação.
  O bit de execução passou a ser pós-condição aplicada antes da observação,
  calculada pelo caminho do plano (uninstall não aplica: o payload já não
  existe no smoke de remoção).
- **Rollback**: o restore da transação publica o payload no modo padrão do
  fs (`0o600`); `engine.rollback` só reconciliava o bit quando o estado
  observado já era `installed` — condição que a detecção nova tornou
  impossível após restore sem bit. A reconciliação passou a valer pela
  presença do payload restaurado, não pelo estado observado.

O módulo fs mantém o modo padrão uniforme `0o600` para backups/restores de
qualquer tipo de arquivo — endurecimento deliberado. O bit de execução é
contrato do deployment engine: quem o promete no apply o reconcilia no
rollback. Replays de recovery continuam podendo commitar payload `0o600`; a
diferença é que agora o estado observa isso, o verify não atesta intacto o que
não executa, e o repair governado reconcilia — degrada com causa registrada,
nunca trava.

## Prova física no host

Concluída em 2026-08-23 contra o artefato instalado `0.1.0a46-5b41f2edbf78`
(daemon convergido, `doctor` com `service.generation` verde):

1. Injeção controlada da falha: `payload` do deployment real
   `2026.04.27-0237a9b88` reduzido a `0o600` (mesma assinatura do replay de
   recovery observado em 2026-08-22).
2. `component status --id citron` ⇒ `degraded`,
   detalhe `payload sem permissão de execução`.
3. `component verify --id citron` ⇒ `verified=false`, `repairable=true`
   (o falso verde anterior desapareceu).
4. `component launch --id citron` ⇒ recusa estruturada `E-COMPONENT-DEGRADED`
   com ação de recuperação sugerida — sem `PermissionError` cru.
5. `component plan --action repair` ⇒ plano v3 metadata-only (~0,56 s),
   aquisição adiada para o apply.
6. `component apply` ⇒ job assíncrono `01M0R265JJ00VHW73TPV3ZH8TN`
   `queued → completed` com estágio final `verified`.
7. Pós-condições: payload `0o700`, estado `installed`,
   `verify` ⇒ `verified=true`, `repairable=false`; segundo plano de repair é
   recusado com erro acionável (`repair exige ['degraded','outdated']`).
8. `launch` abriu o emulador real (pid 952236), captura em
   `02-citron-launch-reparado.png`; `stop` encerrou os grupos de processo.
9. Preservação: snapshot SHA-256 de `~/.config/citron` e
   `~/.local/share/citron*` antes/depois — 259 arquivos; única diferença é a
   rotação própria de log do emulador (`citron_log.txt` ⇄ `.old.txt`) gerada
   pela execução; nand/saves/config byte a byte idênticos.

Nota diagnóstica (ambiente do agente, não defeito do produto): o shell desta
sessão exporta `XDG_STATE_HOME` próprio enquanto o daemon do systemd usa a raiz
canônica; comandos CLI que caem no fallback local gravam planos na raiz do
agente e o apply roteado ao daemon não os encontra (`E-TX-STALE-PLAN`). Interagir
com `env -u XDG_STATE_HOME` alinha as duas pontas. Um job criado pelo caminho
local com worker morto foi reconciliado como `cancelled/recovered`.
