# ADR-0009 — Gerenciamento de privilégios: helper separado com allowlist enum + polkit

**Status:** aceito

## Contexto
PhaseZero usa bridge (`pz_admin_run`: phasezero-admin→bigsudo→sudo -n gated) e sobe scripts com `pz_require_root` re-exec — bom espírito (menor privilégio por comando), mas o bridge aceita comando arbitrário de quem o chama. LinuxToys chama `sudo` dentro dos scripts. §9.6 exige allowlist pequena.

## Alternativas
1. **Binário `steamzero-admin` com ações enum + parâmetros schemados + conteúdos embutidos + polkit por ação** (escolhida).
2. sudo/pkexec por comando (modelo PhaseZero) — contras: a fronteira aceita strings de comando; auditoria difusa; regras sudoers frágeis.
3. Daemon root permanente — contras: superfície residente; desnecessário (ações raras).

## Decisão
Conforme PRIVILEGE-BOUNDARIES.md. Nenhuma string de shell cruza a fronteira; conteúdo privilegiado (units, udev rules) embutido no helper, versionado e assinado com o produto.

## Consequências
Cada ação nova = mudança no helper + policy + testes ST-01; release do helper acompanha o produto (protocolo versionado).

## Revisão
Se o conjunto de ações passar de ~15, reavaliar granularidade das policies polkit.
