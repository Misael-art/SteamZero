# M14 — Plano de distribuição (canais, assinatura, SBOM, downgrade)

**Status:** projeto documental apenas (2026-08-10).  
**Não inclui:** build de release, wheel/wheelhouse, instalação no host, mutação
de `/opt/steamzero`, Flatpak de plataforma, nem código de packaging.

**Critério de marco** (`MILESTONES.md`): Flatpak + canais + update/rollback da
plataforma; demonstração RT-14 verde; **downgrade demonstrado**.

**Dependências de entrada (não bloqueiam o desenho):** host e canais estáveis o
bastante (bootstrap nativo atual em `/opt/steamzero/releases` + `current`);
preferível M10–M12 integrados e verificados, mas o desenho pode fechar antes.

---

## 1. Objetivos e não-objetivos

### Objetivos
1. Publicar a plataforma SteamZero por **canais** (`stable` / `beta` / `dev`) com
   política de troca transacional e reversível.
2. Garantir **integridade e proveniência**: checksums, assinatura, SBOM e
   manifesto amarrados ao `--source-commit`.
3. Update/rollback/downgrade da **plataforma** (não só de adapters de emulador)
   como transação com plano, backup e verify.
4. Coexistir com o bootstrap nativo atual até o Flatpak de plataforma (ou
   substituí-lo de forma controlada).

### Não-objetivos (M14)
- Docs de usuário finais longos (M15).
- Marketplace de temas de terceiros assinados (ADR-0007 / roadmap v2).
- Certificação hardware Deck (G5 / gates operacionais G7-hardware — outro
  significado de “G7”).
- Redistribuir ROMs, BIOS ou dat-files de terceiros.

---

## 2. Canais

Base canônica: `docs/09-operations/RELEASE-CHANNELS.md`.

| Canal | Público | Conteúdo | Lockfile de componentes | Garantias |
|---|---|---|---|---|
| `stable` | padrão | releases testadas (VM+HW conforme matriz) | congelado e testado em conjunto | contrato CLI/API estável; migrações em cadeia; rollback suportado |
| `beta` | voluntários | release candidate | candidato a congelamento | mesmas proteções; bugs esperados |
| `dev` | contribuidores | builds contínuos | pode seguir upstream mais novo (ainda com checksum) | sem promessa de contrato; avisos explícitos |

### Regras operacionais (M14 deve implementar)
1. Troca de canal = **transação** com plano (diff de versão, migrações, espaço) e
   reversível dentro da janela de retenção de backup.
2. Downgrade entre canais **somente** via mecanismo de update/rollback — nunca
   “instalar por cima” sem verify.
3. Versionamento SemVer; janela de suporte: stable N e N−1.
4. **Cadência (Q10 — decisão do operador):** proposta inicial em RELEASE-CHANNELS
   (stable 6–8 semanas, beta contínuo, dev por commit). M14 **não fecha Q10**;
   default documentado até decisão formal.

### Proposta de default até Q10
- `stable`: promove-se apenas de `beta` após checklist RT-14 + gates da seção 6
  do `AGENTS.md` no commit de origem.
- `beta`: tags `vX.Y.Z-beta.N` ou canal de pacote separado.
- `dev`: artefatos CI efêmeros; não ativáveis em host de produção sem flag
  explícita e aviso.

---

## 3. Modelo de assinatura e proveniência

### O que se assina / carimba

| artefato | verificação | quem produz |
|---|---|---|
| Source commit (git SHA completo) | manifesto `source-commit` | CI / `release_host` |
| Wheel / pacote da plataforma | SHA-256 no manifesto + (futuro) assinatura detached | pipeline de release |
| Manifesto de release (schema v2+) | hash do manifesto + assinatura do manifesto | pipeline |
| SBOM CycloneDX | hash no manifesto; opcionalmente cosign/minisign | pipeline |
| Checksums agregados (`SHA256SUMS`) | assinatura do arquivo de checksums | pipeline |
| Lockfile de componentes (adapters) | já pinado por checksum; entra no envelope da release | M10+ |

### Algoritmo e chaves (proposta)
- **Fase M14.a (mínimo viável com bootstrap nativo):** manifesto v2 com
  `source-commit`, hashes de artefatos e entry points de boot — alinhado ao
  instalador atual (`tools/install_host.py` / `tools/release_host.py`). Sem
  contornar preflights de ownership.
- **Fase M14.b (assinatura):** chave ed25519 ou minisign do projeto; chave
  pública embutida no instalador/doctor; assinatura detached do manifesto e de
  `SHA256SUMS`. Rotação documentada; revogação via lista de chaves no repo.
- **Não** reutilizar chaves de desenvolvedor pessoais no canal `stable`.

### Proveniência
- Nenhuma release construída de árvore suja (regra AGENTS.md §4).
- `schemaVersion` moderno; proibido reativar schema v1 para **novas** publicações
  (legado só para rollback de releases antigas).

---

## 4. SBOM

| item | decisão proposta |
|---|---|
| Formato | CycloneDX JSON (já citado no histórico de releases do projeto) |
| Conteúdo | deps Python pinadas, versões Qt/PySide se empacotadas, componentes Flatpak da **plataforma** (não cada ROM) |
| Publicação | anexo da release + hash no manifesto |
| Licenças | cruza com `THIRD-PARTY-NOTICES.md` / `ASSET-INVENTORY.md` |
| Auditoria | `pip-audit` / OSV no CI da tag (já há precedente no worklog de releases) |

M15 consome o SBOM para checklist §17; M14 só **produz e assina**.

---

## 5. Update / rollback / downgrade

Fluxo canônico já esboçado em `UPDATE-AND-ROLLBACK.md`:

```
check → plan → backup → stage → apply → verify → activate → test → commit
```

### M14 deve provar (RT-14)
1. **Update** stable N → N+1 com doctor pós-update ok.
2. **Falha no meio** (migração ou verify) ⇒ restauração íntegra do backup/ponteiro
   anterior (sem estado pela metade silencioso).
3. **Rollback** N+1 → N sob política de dados (RB-6: dados novos não destruídos
   sem aviso).
4. **Downgrade** explícito (mesmo canal ou canal inferior) via o mesmo pipeline,
   nunca overwrite cego.
5. Idempotência: repetir rollback/update não corrompe `current`.

### Bootstrap nativo atual vs Flatpak futuro

| aspecto | hoje (pré-M14 completo) | alvo M14 |
|---|---|---|
| Layout | `/opt/steamzero/releases/<id>` + `current` atômico | manter **ou** espelhar em Flatpak OSTree |
| Ativação | `bigsudo` + `install_host` / `steamzero-host` com ownership markers | mesma disciplina de ownership |
| Rollback | `steamzero-host rollback --release <id>` | + canal assinado; RT-14 |
| Flatpak plataforma | não é o delivery primário no BigLinux host | avaliar ADR-0003; se adotado, commits OSTree para rollback exato |

**Princípio:** M14 não apaga o caminho nativo até o Flatpak provar paridade de
rollback e proveniência. Pode entregar canais/assinatura/SBOM **primeiro** no
bootstrap nativo e só então empacotar Flatpak.

---

## 6. Fases de implementação (código — fora deste documento)

Ordem sugerida para PRs futuros (cada um com gates AGENTS.md):

| fase | entrega | demonstração |
|---|---|---|
| M14.0 | este plano + Q10 marcado | docs only |
| M14.1 | manifesto de canal + metadados de canal no doctor | `doctor` mostra canal/versão/proveniência |
| M14.2 | publicação SBOM + SHA256SUMS no pipeline de release | artefatos na tag |
| M14.3 | assinatura do manifesto (chave de release) | verify no install preflight |
| M14.4 | CLI `platform plan/apply/rollback` unificada aos canais | RT-14 em VM |
| M14.5 | (opcional) Flatpak da plataforma com paridade de rollback | OSTree commit pinado |
| M14.6 | downgrade demonstrado em evidência | docs/diagnostics + RT-14 |

**Proibido nestas fases sem autorização explícita do operador:** `bigsudo`
install/rollback em host de produção; force-push; contornar preflight.

---

## 7. Critérios RT-14 (rascunho testável)

1. Instalação limpa da release R1 no ambiente de prova (VM).
2. Update R1 → R2 com plano confirmado; doctor ok; daemon na identidade R2.
3. Injetar falha de verify em R3 candidato; sistema permanece em R2.
4. Rollback R2 → R1 com smokes e ownership markers.
5. Downgrade R2 → R1 (ou canal beta→stable inferior) com plano honesto sobre
   migrações de dados.
6. Repetir update R1 → R2: idempotente, sem lixo em `releases/`.
7. Evidência em `docs/diagnostics/` com commits, hashes e comandos.

---

## 8. Riscos

| risco | mitigação |
|---|---|
| Assinatura sem rotação vira SPOF | documentar rotação; dual-key transitória |
| Flatpak e nativo divergem | paridade de testes; um “source of truth” de manifesto |
| Q10 indefinido atrasa UX de canal | defaults acima até decisão |
| Release de árvore suja | preflight AGENTS + install_host recusam |
| Competição com M10 VM em CI/host | RT-14 em VM dedicada; não no meio de evidência DEBT-A7 |

---

## 9. Relação com documentos existentes

- `docs/09-operations/RELEASE-CHANNELS.md` — política de canais (canônico)
- `docs/09-operations/UPDATE-AND-ROLLBACK.md` — fluxo transacional
- `docs/09-operations/HOST-INSTALL.md` / `RELEASE-HOST-AUTOMATION.md` — bootstrap atual
- `docs/09-operations/RELEASE-LEDGER.md` — auditoria retrospectiva
- `docs/OPEN-QUESTIONS.md` Q10 — cadência (pendente operador)
- `docs/11-legal/ASSET-INVENTORY.md` — entra no envelope de notices da release
- `AGENTS.md` §1 e §4 — autorização de install e proibição de build de release
  sem pedido

---

## 10. Decisões que exigem o operador

1. **Q10** — cadência e nomes finais de canais (aceitar proposta ou alterar).
2. **Algoritmo de assinatura** — minisign vs cosign/ed25519 e custódia da chave
   `stable`.
3. **Flatpak de plataforma no M14 ou só nativo+assinatura** — se o host BigLinux
   permanece nativo por mais um ciclo.
4. **Quando** autorizar a primeira publicação assinada e o primeiro RT-14 em VM
   dedicada.

Até essas decisões, este documento é o contrato de desenho; implementação de
código e release continuam sob autorização explícita na thread.
