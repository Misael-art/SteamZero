# SECURITY-REQUIREMENTS — requisitos verificáveis

Cada SR- tem verificação automatizável (lint, teste ou auditoria de CI).

## Código

- SR-01 Bash (apenas shims): `set -euo pipefail` + trap de erro; exceções esperadas tratadas explicitamente (`|| true` só com comentário do porquê). Verificação: shellcheck + lint próprio.
- SR-02 Proibidos: `eval`, `curl|bash`, `wget|sh`, expansão de string como comando, dispatch por nome de função vindo de dados, `rm -rf` sem inventário do plano. Verificação: lint em CI (grep estruturado + AST bash).
- SR-03 Python: sem `shell=True` com interpolação; comandos como listas (arrays); sem `pickle` de dados externos; `defusedxml` para XML.
- SR-04 Todos os inputs externos validados por schema antes de uso (API, manifests, configs importadas).

## Filesystem

- SR-05 Toda escrita via `core.fs`: atomic write (tmp+fsync+rename), no mesmo FS do destino.
- SR-06 Containment: paths resolvidos com realpath e verificados contra a raiz permitida da operação; symlinks de dados de usuário abertos com O_NOFOLLOW quando aplicável.
- SR-07 `umask 077`; state dir 0700; logs 0600 (herda PhaseZero common.sh:4,13,18).
- SR-08 Nada de escrita direta em arquivos críticos de terceiros (shortcuts.vdf, es_settings.xml...) sem backup + parser estruturado + verify.

## Rede e supply chain

- SR-09 Downloads: HTTPS, checksum obrigatório (falha, não warning — AC-IN-01), tamanho máximo declarado, timeout e low-speed limit.
- SR-10 Sem execução de conteúdo baixado em runtime sem: versão pinada + hash + origem + licença + aprovação no manifesto (§15).
- SR-11 Dependências com lockfile + hash; SBOM por release; scan de vulnerabilidade em CI.

## Privilégio

- SR-12 Menor privilégio (PRIVILEGE-BOUNDARIES); helper com allowlist enum; nunca `sudo` de bloco; nunca shell atravessando a fronteira privilegiada.

## Segredos e privacidade

- SR-13 Segredos nunca em logs, nunca em argv, nunca no state.db em claro; tipo `Secret` com repr mascarado; keyring do sistema quando disponível.
- SR-14 Keys/BIOS/firmware: conteúdo nunca copiado para logs/relatórios; referências por hash truncado.
- SR-15 Support bundle: anonimizado, revisável pelo usuário antes de exportar (nunca envio automático).

## Concorrência e recuperação

- SR-16 Locks com lease + dono; detecção de lock órfão.
- SR-17 Journal WAL para toda transação; recovery determinístico testado com kill em cada etapa.

## API local

- SR-18 Socket UNIX 0700 + verificação de peer credentials (SO_PEERCRED); sem bind TCP por padrão; ações mutáveis exigem confirmToken.
- SR-19 Sem nomes de função/ação arbitrários: dispatch apenas de ações registradas (P4).

## Auditoria

- SR-20 Logs estruturados com correlationId/operationId; ações privilegiadas com audit log próprio append-only.
