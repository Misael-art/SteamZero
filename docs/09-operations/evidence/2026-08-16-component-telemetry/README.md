# Componente: telemetria local sanitizada

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base do incremento: `e75b091`

## Hipótese a reproduzir

O job informa progresso e erro, mas não preserva fatos diagnósticos sobre DNS,
proxy, ambiente e executor. Além disso, o token já validado ainda é copiado para
`job.params_json`, ampliando desnecessariamente a custódia da autorização.

A reprodução deve exigir diagnósticos locais úteis sem URL completa, endereço
IP, valor de proxy, variável arbitrária ou token. O worker deve continuar
recuperável usando somente `planId` e a autorização já persistida no plano
protegido, mantendo compatibilidade com jobs legados.

## Reprodução vermelha

Com os testes de regressão adicionados, a execução focada falhou em três pontos
antes da correção:

- `transfer_observer()` recusava o callback `diagnostic`;
- a falha DNS não produzia fato diagnóstico;
- `job.params_json` ainda continha `confirmToken`.

Resultado: `3 failed, 21 passed`. A falha reproduziu o contrato ausente sem rede
real e sem alteração no estado real monitorado pelo runner isolado.

## Causa raiz

O observador de transferência carregava somente bytes e cancelamento. O job
persistia o token recebido pela bridge para que o worker futuro pudesse chamar
`apply()`, embora o mesmo token já estivesse guardado no envelope de plano com
permissões do estado local. Não havia uma porta interna para o worker reler essa
autorização e reexecutar todas as validações do apply.

## Correção

- `core.net` emite fatos `starting`, `completed` e `failed` com host sem
  caminho/query, estado DNS, esquemas de proxy e nomes de variáveis relevantes;
  valores, IPs e variáveis arbitrárias nunca entram no payload;
- o job grava executor/adapter e os fatos de rede em checkpoints duráveis e os
  devolve em `diagnostics`, inclusive em falha ou cancelamento;
- jobs novos não persistem `confirmToken`; o worker relê o token do plano e
  passa novamente por TTL, uso único, fingerprint e validação de contexto;
- jobs legados que já continham o token continuam recuperáveis.

## Evidência automatizada

- foco unitário + integração real do lifecycle: `88 passed`;
- Ruff focado: verde;
- Ruff format focado: verde;
- mypy: `223 source files`, sem issues;
- primeira suíte completa: `4716 passed, 10 skipped`, com uma única falha de
  governança esperada porque o `scopeDigest` ainda descrevia o estado anterior;
- estado real antes/depois da suíte: idêntico (`11918` arquivos, `1942`
  diretórios, `1100955063` bytes, mesmo `max_mtime_ns`).
- após corrigir o digest, a suíte completa terminou com `4717 passed, 10
  skipped` em `1212.37s`;
- nessa execução final, o runner detectou mudança concorrente em logs/WAL do
  estado real e identificou os três donos preexistentes (daemon, bridge UI e
  QML da release ativa). O gate passou, mas registrou que a atribuição de
  ausência de escrita da suíte fica degradada enquanto esses processos externos
  permanecem ativos.
- Ruff em `src tools tests`, format-check dos `475` arquivos, mypy nas `223`
  fontes, independência, fronteiras, status-check e diff-check: verdes.

Nenhum build de release, instalação, rollback, reboot ou mutação do host foi
executado neste incremento.
