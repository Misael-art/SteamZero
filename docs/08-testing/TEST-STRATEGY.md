# TEST-STRATEGY

## Pirâmide e ferramentas

| Camada | Escopo | Ferramentas | Gate |
|---|---|---|---|
| Unit | parsers, schemas, path safety, plan/diff, hashes, máquinas de estado | pytest + hypothesis (property-based p/ paths e archives) | CI todo PR |
| Integração | pipeline transacional real em FS temporário; adapters contra fixtures; State Store; job manager | pytest + containers/chroots por distro-família | CI todo PR |
| Injeção de falhas | FAILURE-INJECTION.md (kill em cada etapa, ENOSPC, rede, mounts) | harness próprio (fault injection por LD_PRELOAD/fuse/cgroup + mocks de rede) | CI diário + pré-release |
| Sistema | fluxos completos em VMs (SteamOS-like, Fedora, Arch, Bazzite, Ubuntu) | imagens de VM versionadas | pré-release |
| Hardware | STEAM-DECK-HARDWARE-MATRIX.md | checklist manual assistido por `steamzero doctor --json` | pré-release por canal |
| UI | focus graph, navegação por input sintético, screenshots por escala | UI-TESTS.md | CI todo PR de UI |
| Segurança | SECURITY-TESTS.md | fuzzing + suíte de vetores | CI diário |
| Rollback | ROLLBACK-TESTS.md (critério §13.6) | harness transacional | CI todo PR que toque mutação |

## Princípios

1. **Análise estática ≠ comprovação em hardware** (§20): resultados de VM não marcam itens de hardware como validados; o relatório de release distingue `verified-vm` de `verified-hw`.
2. **Golden files** para contratos (envelope JSON, eventos NDJSON, planos) — mudança de contrato aparece como diff explícito no PR.
3. **Fixtures sintéticas de conteúdo:** dumps falsos gerados (headers válidos, conteúdo aleatório) — nenhum conteúdo protegido real no repositório ou CI (CONTENT-POLICY).
4. **Idempotência testada por padrão:** todo teste de operação roda a operação 2× e compara estado (RNF-04).
5. **Testes de recuperação são de primeira classe:** cada operação nova entrega junto seus casos de kill/rollback (DoD).
6. Lição dos fontes: PhaseZero mostra o valor de suíte grande (122 arquivos) rodando em CI; EmuDeck mostra o custo da ausência. Meta de cobertura: 90% no núcleo transacional/core.fs; 80% domínio; adapters cobertos por contrato (suíte genérica que todo adapter deve passar).
