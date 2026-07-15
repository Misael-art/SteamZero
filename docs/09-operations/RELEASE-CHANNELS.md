# RELEASE-CHANNELS — canais de release

Precedente: RetroDECK opera `main` (stable) + `cooker` (dev) com instalador de release específica; PhaseZero versiona com tags de release. O Unified formaliza três canais (§10.1):

| Canal | Público | Conteúdo | Lockfile de componentes | Garantias |
|---|---|---|---|---|
| `stable` | P1 (padrão) | releases testadas (VM+HW conforme matriz) | congelado e testado em conjunto | contrato CLI/API estável; migrações testadas em cadeia; rollback de release suportado |
| `beta` | P2 voluntários | release candidate | candidato a congelamento | mesmas proteções; bugs esperados |
| `dev` | contribuidores | builds contínuos | pode seguir upstream mais novo (ainda com checksum) | sem promessa de contrato; avisos explícitos na UI |

## Regras

1. Troca de canal é uma transação com plano (mostra o que muda, inclusive migração de dados) e é reversível dentro da janela de retenção do backup.
2. Downgrade entre canais: suportado somente via mecanismo de UPDATE-AND-ROLLBACK (nunca "instalar por cima").
3. Versionamento da plataforma: SemVer; migrações de dados amarradas a versões (MIGRATION-VERSIONING); janela de suporte: stable N e N-1.
4. Cadência: pendente de decisão (Q10) — proposta inicial: stable a cada 6–8 semanas, beta contínuo, dev por commit.
5. Cada release publica: changelog orientado a usuário, SBOM, checksums assinados, relatório de testes (incluindo o que ficou `verified-vm` vs `verified-hw`).
