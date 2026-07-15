# SECURITY-TESTS — testes de segurança

| ID | Alvo | Teste | Critério |
|---|---|---|---|
| ST-01 | Helper privilegiado | fuzzing de parâmetros (tipos, ranges, traversal em uuid/unitId, ações inexistentes, protocolo antigo) | 100% rejeição limpa (E-PRIV-*); zero execução; audit log registra tentativas |
| ST-02 | API local | conexão de outro UID (deve falhar no peer cred); replay de confirmToken usado; token expirado; método fora da allowlist; JSON malformado; payload gigante | rejeição com códigos corretos; daemon estável |
| ST-03 | Logs/bundle | canary secrets (tokens sintéticos plantados) atravessando todos os fluxos | zero ocorrência em logs, exports e bundles (scanner automático) |
| ST-04 | Supply chain | manifesto sem sha256; hash errado; downgrade de versão pinada; redirect malicioso no download | AC-IN-01; recusa; sem execução de artefato não verificado |
| ST-05 | Adapter de terceiro | manifesto com URL suspeita, capability não permitida, tentativa de hook de código no v1 | carregamento recusado/degradado a declarativo; badge não-verificado |
| ST-06 | Scraping | payload com magic bytes errados, nome com traversal/bidi, imagem 2GB | sanitização; limites; quarentena |
| ST-07 | Segredos | leitura de token via API (não deve existir rota); dump do state.db não contém segredos | write-only confirmado; keyring usado quando disponível |
| ST-08 | Path safety | suíte de vetores de PATH-SAFETY (property-based com hypothesis) | containment 100% |
| ST-09 | Archives | corpus de zips/7z/tars hostis (bombs, traversal, links, sparse) | safezip resiste; recursos limitados (tempo/memória) |
| ST-10 | Lint estrutural | proibições de MODULE-BOUNDARIES/SR-02/SR-03 (eval, shell=True interpolado, escrita fora de core.fs) | CI falha ao violar |

Rotina: ST-01/02/08/09 diários no CI; corpus de fuzzing acumulativo; findings viram FI novos.
