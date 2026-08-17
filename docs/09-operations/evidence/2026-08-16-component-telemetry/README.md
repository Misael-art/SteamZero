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

## Validação read-only no host real

Fonte limpa: `b32ac7e7ab6408c95d599011bac86880d52bf6d9`.

A sonda executou o código diretamente deste worktree, sem usar a release
instalada. Duas URLs brutas preliminares devolveram `E-NET-HTTP: HTTP 404` e
foram descartadas como alvo inválido; a prova válida usou uma página pública
pequena e um domínio `.invalid` reservado:

- sucesso HTTPS real: `11506` bytes e `2` amostras de progresso;
- DNS do sucesso: `resolved` para `www.python.org`;
- DNS negativo real: `failed`, `E-NET-OFFLINE`, apenas o hostname reservado;
- ambiente: somente o nome permitido `FLATPAK_ID`, nunca seu valor;
- query, caminhos e três valores-canário ausentes do JSON (`secretLeak=false`).

Uma segunda sonda criou o State Store em diretório XDG temporário e executou um
`component.apply` real pelo `ComponentJobService`:

- estado final `completed` / projeção `succeeded`;
- executor persistido e publicado: `engine`;
- chaves persistidas: `action`, `adapterId`, `executor`, `planId`;
- `confirmToken` ausente de `params_json` e de toda a projeção;
- diretório temporário removido automaticamente ao final.

As sondas não usaram endpoint mutável do daemon instalado, não tocaram o State
Store do operador e não instalaram, repararam ou removeram componente.
