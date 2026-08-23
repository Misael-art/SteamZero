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

Pendente no fechamento funcional; registrada na sequência com o ciclo:
detecção do estado degradado no deployment real, repair governado por job,
bit restaurado, launch/stop e preservação byte a byte dos dados do aplicativo.
