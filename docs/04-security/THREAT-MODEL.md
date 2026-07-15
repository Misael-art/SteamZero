# THREAT-MODEL

## Ativos

A1 dados do usuário (saves, ROMs próprias, BIOS próprias, keys próprias, mídia); A2 integridade do sistema (configs, boot não é escopo, serviços user); A3 credenciais cloud; A4 integridade da própria plataforma (binários, adapters, atualizações); A5 privacidade (paths, hábitos de jogo).

## Atores/superfícies

S1 arquivos fornecidos pelo usuário (archives, dumps, mídia importada de pendrive); S2 rede (releases de emuladores, scraping de metadados, cloud); S3 processos locais de outros apps do mesmo usuário; S4 manifestos de adapter de terceiros; S5 helper privilegiado; S6 cadeia de build/distribuição.

## Ameaças (STRIDE) e mitigações

| ID | Ameaça | Ativo | Mitigação | Verificação |
|---|---|---|---|---|
| T-01 | Archive malicioso no import (zip bomb, traversal `../`, symlink p/ fora) | A1,A2 | safezip com limites (razão, entradas, profundidade), extração confinada a staging, O_NOFOLLOW, containment por realpath (precedente PhaseZero `safezip.py`; guard common.sh:748-764) | FAILURE-INJECTION FI-16..18 |
| T-02 | Download adulterado (MITM, release comprometida) | A4 | HTTPS + sha256 pinado no manifesto/lockfile; sem "latest" fora do canal dev; assinaturas quando upstream fornece | SECURITY-TESTS ST-04 |
| T-03 | Scraper de mídia retorna payload malicioso (imagem forjada, path no nome) | A1 | sanitização de nomes, tipos verificados por magic bytes, tamanho máximo, sem execução | ST-06 |
| T-04 | Escalada via helper privilegiado (parâmetro forjado) | A2 | allowlist enum + schemas + conteúdos embutidos; polkit por ação; audit log | ST-01 fuzzing AC-PR-01 |
| T-05 | Processo local do mesmo usuário chama a API e dispara ações destrutivas | A1,A2 | socket 0700 no runtime dir do usuário + peer credentials; ações destrutivas exigem confirmToken exibido por UI/CLI legítimos; authz local (06-api/AUTHORIZATION-MODEL) | ST-02 |
| T-06 | Manifesto de adapter de terceiro malicioso (URL para binário trojan) | A4,A2 | v1: manifests declarativos apenas, sha256 obrigatório, badge não-verificado + confirmação; sem código de terceiros | ST-05 |
| T-07 | Vazamento de keys/BIOS/paths em logs ou support bundle | A5,A1 | política de logging (nunca keys/saves), tipos Secret, anonimização de paths, bundle revisável antes de exportar | ST-03 auditoria de logs |
| T-08 | Roubo de token cloud do State Store | A3 | secrets fora do state.db (keyring do sistema quando disponível; senão arquivo 0600 cifrado com chave local), write-only na API | ST-07 |
| T-09 | Rollback como vetor (restaurar backup adulterado) | A2 | backups com manifesto de hashes verificado na restauração; diretório 0700 | ROLLBACK-TESTS RT-05 |
| T-10 | Supply chain do próprio produto (dependência PyPI comprometida) | A4 | lockfiles com hash, SBOM, CI com scan, builds reproduzíveis (15-supply) | pipeline CI |
| T-11 | TOCTOU entre plan e apply | A2 | fingerprints de precondição revalidados no apply (AC-TX-01) | RT/FI |
| T-12 | DoS local: staging/backups enchem o disco | A2 | quotas por operação, GC de backups, preflight de espaço com margem | FI-06 |

## Fora do modelo (aceito)

- Root local malicioso (game over por definição).
- Usuário executando conscientemente conteúdo malicioso fora da plataforma.
- Ataques físicos ao hardware.

## Revisão

Threat model revisitado a cada ADR novo que toque S1–S6 e a cada fase do roadmap.
