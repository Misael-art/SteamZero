# Componente físico Flatpak: pré-requisito de recovery do Azahar

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base do incremento: `93ebeb4`

## Escopo deste incremento

Fechar o defeito que mantinha autorizações históricas de componente em
`pending` indefinidamente e provar a migração no state home real antes de
iniciar o ciclo físico do Azahar. A plataforma instalada não foi substituída,
nenhum componente foi instalado ou removido e não houve push, release ou
reboot.

## Reprodução vermelha

O baseline físico encontrou:

- 28 planos Flatpak v1 pendentes e expirados;
- 22 envelopes de componente v2/v3 pendentes e expirados;
- cinco planos transacionais vinculados por `transactionPlanId` a envelopes de
  componente, dentro de uma contagem bruta de 1882 planos transacionais
  pendentes;
- três operações de componente, todas já `rolled-back`;
- dez planos pendentes do Azahar, componente ausente e diretório de dados
  `~/.var/app/org.azahar_emu.Azahar` inexistente.

Os testes vermelhos focalizados provaram dois casos ausentes: plano Flatpak v1
expirado sem operação e envelope externo expirado sem efeito delegado. A
primeira implementação também expôs uma colisão de schema: planos Flatpak e
planos transacionais históricos usam `schemaVersion: 1`.

## Causa raiz e correção

O recovery existente encerrava operações interrompidas, mas não varria planos
Flatpak v1 órfãos nem envelopes v2/v3 expirados sem efeito. A correção:

- reconhece plano Flatpak v1 pelo conjunto completo de campos Flatpak, sem
  consumir planos transacionais de mesmo schema;
- preserva autorização nova, ainda válida e nunca iniciada;
- aborta autorização expirada sem operação;
- reconcilia plano Flatpak com operação já terminal;
- aborta envelope de componente expirado sem delegado;
- mantém o vínculo existente para terminalizar os cinco planos transacionais
  que pertenciam a envelopes de componente.

## Prova automatizada

- Foco: `tests/integration/test_flatpak_executor.py` e
  `tests/integration/test_component_lifecycle.py`: `99 passed`.
- Gates focados: Ruff check/format, mypy (`223` arquivos), independence e
  boundaries: aprovados.
- Suíte funcional anterior: `4729 passed, 10 skipped`; o guardião terminou com
  código 86 porque comandos de acompanhamento continham o nome do produto e
  foram classificados como escritores. Esse resultado não foi aceito como
  gate integral.
- Única repetição: unidade transitória neutra
  `sz-gate-plan-recovery-20260816.service`, sem acompanhamento que casasse com
  o detector: `4729 passed, 10 skipped in 1004.73s`, `ExecMainStatus=0`.
- O guardião confirmou state home idêntico antes/depois: 11916 arquivos, 1942
  diretórios, 1097425649 bytes e mesmo `max_mtime_ns`.
- Log preservado em `/tmp/sz-gate-plan-recovery-20260816.log`, SHA-256
  `d7087a3ffa42de3f5477230ff8d4d967a3b08b3b15adfc82006a540a2d026b36`.

## Prova física governada

O host real foi mutado somente por `ComponentLifecycle.plan_recovery()` seguido
de `apply_recovery()`. O plano de recovery terminou `applied`; a API retorna
`status: ok`, distinção que fez a sonda encerrar depois da aplicação, sem
reaplicação.

Resultados observados:

| Invariante | Resultado |
|---|---|
| Operação ativa fora do escopo | nenhuma antes do plano; precondição da sonda aprovada |
| Planos Flatpak expirados | 28 `aborted`, zero pendente |
| Envelopes de componente expirados | 22 `aborted`, zero pendente |
| Transações delegadas | cinco `aborted`; todos os cinco arquivos alterados estavam vinculados por `transactionPlanId` |
| Transações realmente genéricas | 1877 pendentes antes/depois; nenhuma foi alterada |
| Operações já terminais | três `rolled-back`, SHA-256 `a1b8ba631efe67b310cc672bbba82c792dfbeea18350212e4062d1d60da1668e`; zero arquivo com mtime igual ou posterior ao recovery |
| Deployments Flatpak | 17 refs; nenhum evento no `flatpak history --user` durante a janela do recovery; Azahar continuou ausente |
| Dados do Azahar | inexistentes antes/depois: zero arquivo e zero byte |
| Segredos | busca nos relatórios não encontrou token, senha, bearer, authorization ou proxy; `confirmToken` ficou somente em memória |

Relatórios sanitizados preservados durante a sessão:

- `/tmp/sz-legacy-plan-recovery-post-20260816.json`, SHA-256
  `ff6abb477256da313f8a3cbe84b316b289ebbc873fe1eecce62df08f0ffdc930`;
- `/tmp/sz-legacy-plan-recovery-linkage-20260816.json`, SHA-256
  `13c4a62f8d2e66659a282d1d17810d50aa62d395cfe243513fc52916cff9ca9b`.

## Estado e próxima ação

O defeito de recovery legado está fechado. O ciclo funcional do Azahar ainda
não começou neste incremento; a próxima ação é baseline, plan metadata-only,
install, verify, segunda instalação idempotente, repair, falha controlada,
rollback e uninstall com preservação de dados.
