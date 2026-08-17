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

## Ciclo físico individual do Azahar

O ciclo foi executado depois do commit `6fdcb72`, sempre com o código commitado
da branch no `PYTHONPATH`, state home real e Flatpak do usuário real.

### Baseline e plano

- `status=missing`, zero recovery ativo, zero job do Azahar, dez planos antigos
  `aborted` e três operações antigas `rolled-back`;
- commit pinado `fd0b3050e4da6a7df8915f63fb8c1d551c7ca8c684568dc62c1681fd316a288c`
  resolvido pelo Flathub em 0,249 s;
- 249166667776 bytes livres, 17 deployments Flatpak e nenhum dado do Azahar;
- plano install v3 gerado em 0,049006 s, `delegated={}`; hash de deployments e
  dados idêntico antes/depois, provando planejamento metadata-only.

### Install, verify e idempotência

- install assíncrono: 23,057 s, job `completed`, operação `committed`, estágio
  final `verified`, commit instalado igual ao pinado;
- verify independente: `installed`, `verified=true`, origem Flatpak;
- o smoke real criou oito arquivos de dados, 2196717 bytes;
- segunda instalação: plano `action=noop` em 0,042035 s, job `completed` em
  0,948 s, sem nova operação; deployment e dados não mudaram.

### Repair físico

Como repair é corretamente recusado para deployment íntegro, um drift foi
criado pelo próprio lifecycle, sem comando manual de mutação:

1. o Flathub confirmou o commit histórico
   `c41f1e818b0387610e018598cf31c57cff6172235726d3b1cf87b29ecc3e073a`;
2. um manifesto somente em memória, pinado nesse commit, gerou plano v3
   metadata-only em 0,005166 s;
3. o job governado instalou e verificou o commit histórico em 15,924 s;
4. o manifesto oficial observou `degraded`, `repairable=true`;
5. o plano `repair` oficial foi metadata-only em 0,095281 s;
6. repair concluiu em 5,436 s, restaurou `fd0b3050…`, terminou
   `verified=true` e deixou tanto a operação Flatpak quanto o marcador durável
   de repair em `committed`.

Os dados continuaram presentes durante todo o drift/repair. O smoke acrescentou
estado próprio do aplicativo, elevando a contagem para nove arquivos, sem
apagamento.

### Falha controlada e rollback

Um novo plano governado para o commit histórico recebeu uma porta Flatpak real
com falha injetada somente no `smoke`, depois do deploy. Resultado:

- job `rolled-back` em 7,426 s;
- erro estruturado `E-COMPONENT-UPDATE-ROLLEDBACK`;
- progresso chegou ao estágio `smoke` (3/4);
- operação durável `rolled-back` e plano `aborted`;
- deployment restaurado ao commit oficial `fd0b3050…`;
- nove arquivos, 2196717 bytes, mtime e SHA-256 de dados exatamente iguais
  antes/depois (`94c22c966c34aaa60ffa097c0874ed9c7ae3fc3d3481eaa7acc6f04bfaa7b93b`).

### Uninstall e estado final

- plano uninstall v3 metadata-only em 0,044543 s;
- job `completed` em 2,929 s, operação `committed`;
- Azahar voltou a `missing`, sem deployment e sem recovery ativo;
- os nove arquivos/2196717 bytes mantiveram o mesmo mtime e SHA-256 integral;
- cinco jobs bem-sucedidos e um job `rolled-back` registram o ciclo;
- nenhuma unidade transitória terminou com erro;
- a busca exata nos relatórios não encontrou `confirmToken`, senha, segredo,
  authorization, bearer ou valor de proxy.

O Flatpak manteve `org.kde.Platform/x86_64/6.9` após remover o aplicativo. É um
runtime compartilhável, não o deployment do Azahar: o inventário final tem 18
refs em vez das 17 iniciais. Ele não foi removido manualmente nem por
`flatpak uninstall --unused`, porque limpeza global de runtimes não pertence ao
ciclo de um componente individual.

## Artefatos sanitizados da sessão

Os principais registros temporários e seus SHA-256 foram:

| Etapa | Arquivo | SHA-256 |
|---|---|---|
| baseline | `/tmp/sz-azahar-baseline-20260816.json` | `8a2dfa0bf6259a613389bb5387338c9c05cf1ba5c36948c10b978442e5843833` |
| install | `/tmp/sz-az-install-20260816.log` | `13c4a4e193fe70a420d4c9ffc92641dc8a898627a6f51ac303e529dfb9099b54` |
| idempotência | `/tmp/sz-az-idempotent-20260816.log` | `198d7baaca2c1b78107b5a26a71181230d97579d75a0f41366e8a1511cce4814` |
| drift | `/tmp/sz-az-drift-20260816.log` | `4bf0deae28b5d98d9b95c2b5306a3bce5f1eaa5d2fca958cc84376e9348393f6` |
| repair | `/tmp/sz-az-repair-20260816.log` | `122d14096883c459f87a684533fec9140f49bdbbe097565b4caa0a0eccf28da9` |
| falha/rollback | `/tmp/sz-az-controlled-failure-20260816.log` | `616d8e3891c1844d43d8e24f94893f643baebfac66978fa8de80ffcc3f32006a` |
| uninstall | `/tmp/sz-az-uninstall-20260816.log` | `1d63c45cb054f28bcef9a58baba956e07e5f9d69310e5215baae05d653c0923a` |
| estado final | `/tmp/sz-azahar-final-20260816.json` | `3890c99c80f36b8e5418b51677132b3d37159b4761c3b97de990a55502c2b2aa` |

## Estado e próxima ação

Recovery legado e ciclo físico individual do Azahar estão fechados. Azahar é o
primeiro resultado físico completo da matriz (1/33). A próxima ação é executar
o próximo adapter Flatpak individual, mantendo o runtime 6.9 observado como
fato de inventário, não como deployment instalado do Azahar.
