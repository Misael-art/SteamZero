# SUPPLY-CHAIN — cadeia de suprimentos

## Entradas da cadeia

1. **Dependências do produto** (Python, Godot, libs): lockfile com hashes; atualização por PR revisado; scan (osv/pip-audit) em CI; SBOM (SPDX) publicado por release.
2. **Emuladores/ferramentas instalados pela plataforma:** manifesto por adapter com `{origem, versão pinada, sha256, licença}`; canal stable usa **lockfile de componentes** publicado com cada release da plataforma (testado em conjunto); canal dev pode seguir releases upstream mais novas, ainda com checksum obtido de fonte independente do binário quando o upstream publica.
3. **Assets** (BIOS-db de hashes conhecidos, templates): versionados no repo, revisáveis por diff.

## Regras (herdam §15 do prompt mestre)

- Sem dependências "latest" sem controle; sem submódulo flutuante.
- Nenhum componente baixado/executado em runtime sem: versão + hash + origem + licença + assinatura quando disponível + aprovação no manifesto.
- Flatpak é pinado pelo commit OSTree completo; o plano confirma a disponibilidade desse
  commit via remote antes de qualquer mutação e o Flatpak valida a confiança configurada
  do remote. O lockfile também congela o hash canônico do manifesto.
- Builds reproduzíveis como meta (Flatpak ajuda: manifest declara fontes com hash — modelo RetroDECK `net.retrodeck.retrodeck.yml`); diferenças documentadas quando não atingível.
- Artefatos de release assinados (minisign/cosign) + attestation de proveniência (SLSA-style) no CI.
- Canais: `stable` (lockfile congelado), `beta` (candidato), `dev` (contrato frouxo, avisos explícitos) — política em 09-operations/RELEASE-CHANNELS.md.

## Anti-padrões dos fontes que ficam banidos

- `install.sh | bash` como método de instalação primário (EmuDeck upstream) — instalação oficial será Flatpak/pacote com checksum publicado.
- Resolução de "latest" da API GitHub no cliente sem pin (`getReleaseURLGH`, helperFunctions.sh:413) — substituída pelo lockfile de componentes.
- Vendorizar binários no repo sem manifesto de origem (PhaseZero `linuxtoys-bin/`) — se vendorizar, com manifesto {origem, hash, licença}.

## Incidentes

Runbook: revogar release (canal aponta para versão anterior — rollback de plataforma via 09-operations/UPDATE-AND-ROLLBACK.md), publicar advisory, rotacionar chaves se assinatura comprometida.
