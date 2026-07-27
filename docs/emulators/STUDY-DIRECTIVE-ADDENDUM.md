# Adendo ao direcionador de estudo — o que dois dossiês ensinaram

Este documento **não substitui** o direcionador de estudo. Ele o corrige e o
complementa com o que a Onda 0 (`switch`) e o primeiro item da Onda 1 (`nes`)
produziram entre 2026-07-24 e 2026-07-25.

Quem receber o direcionador original **deve ler este adendo junto**. Sem ele,
repete quatro erros que já foram pagos.

---

## A. Correções ao texto do direcionador

| # | O direcionador diz | Realidade no repositório | Ação |
|---|---|---|---|
| A1 | "FM correspondente a propor (aditivo, **FM-62+**)" | O maior FM do repositório é **FM-26** (`docs/03-architecture/FAILURE-MODES.md`). A citação de `FM-22` no mesmo parágrafo confere e existe | Propor **FM-27+**. Já usados por este ciclo: FM-27, FM-28, FM-29 — o próximo dossiê começa em **FM-30** |
| A2 | "Onda 0 (já em curso): Switch — **revisar** dossiê existente" | Não existia dossiê nem o diretório `docs/emulators/` | Já resolvido: `switch.md` foi **criado**. A Onda 0 está fechada em `verde` |
| A3 | §1 exige ler `IMPLEMENTATION-REPORT.md`, `COOP-ONLINE`, `THEME-RUNTIME`, `DESKTOP-EXPERIENCE`, `EXPANSION-SUPER-PROMPT` | **Nenhum dos cinco existe.** Os outros onze existem | Não inventar (§9.5 proíbe redesenhar arquitetura). Onde um dossiê dependeria deles, declarar a dependência e parar. Netplay depende de `COOP-ONLINE` e por isso fica fora de qualquer WI até ela existir |
| A4 | Pressupõe pesquisa web livre | `WebSearch` e `WebFetch` falham neste ambiente (modelo indisponível) | Pesquisar pelo **navegador**, que funciona. Muito mais lento por fonte — dimensione a onda por isso |

## B. Lições de método — as que custaram retrabalho

Estas não estão no direcionador e deveriam estar. Cada uma corresponde a uma
afirmação errada que este ciclo publicou e teve de corrigir.

### B1. Comentário em script de referência é hipótese datada, não fato

Dois erros (`CORR-2`, `CORR-3` do ledger) vieram de copiar comentários de uma
árvore de scripts legados: "melonDS não tem duas janelas" (tem, desde a 1.0) e
"Azahar usa `layout_option=5`" (é `4`; o `5` é HybridScreen). O script estava
certo quando foi escrito e **envelheceu em silêncio**.

**Regra:** material de referência entra como *pista a confirmar*. Nunca citar
como fonte sem reverificar no upstream, com data.

### B2. Versão da documentação ≠ versão do binário

`mesen.ca/docs` serve documentação da linha 0.9.9 (2020) para um projeto cuja
estável é 2.2.1 (2026). Metade dos fatos de comportamento do MesenCE teve de sair
de **leitura de código-fonte**, não de documentação.

**Regra:** toda resposta baseada em documentação declara a **versão do documento**.
Se a documentação for de linha anterior, o fato vira `[validar no spike]` ou se
busca no código, com o caminho do arquivo como fonte.

### B3. Não estender o padrão de um projeto a outro por analogia

`CORR-1`: afirmei "AppImage pinado por SHA-256" para o MesenCE porque era o
padrão dos três manifestos de Switch. A estável do MesenCE **não tem AppImage**
(só `.zip`), e o projeto **não publica hash nenhum**.

**Regra:** proveniência se verifica por projeto. O padrão do vizinho não é
evidência.

### B4. Cruzar fontes é onde estão os achados que importam

O achado de maior impacto do ciclo (**FM-29**) não estava em fonte nenhuma: veio
de cruzar "o MesenCE endereça config por jogo pelo nome do arquivo" com "o WI-5
renomeia ROMs para o padrão No-Intro". Conclusão: o WI-5 órfã silenciosamente
todas as configs por jogo.

**Regra:** ao fechar um dossiê, cruzar explicitamente cada superfície de arquivo
descoberta contra os WIs já planejados na porting-directive. Perguntar: *algum WI
existente mexe nisto?*

## C. Achados transversais — não redescobrir por sistema

Valem para toda a fila. Cite-os; não repita a pesquisa.

### C1. O compositor do Game Mode é restrição de primeira classe

Verificado em 2026-07-25:

- **Popups de certos toolkits não renderizam.** A correção upstream do Avalonia
  foi revertida (PR #14573, 2024-02-10); a issue de dropdowns do Gamescope (#327)
  está aberta desde 2022. Os fixes de junho/2026 (#2176, #2211) tratam dropdowns
  de processos filhos, **não** o caso genérico.
- **É single-output e single-focus.** As issues #645 e #737 seguem abertas; não
  há seleção de monitor nem spanning na série 3.16.x.

**Consequência dupla:** (a) configuração por GUI do emulador é inviável em Game
Mode — o que **valida a tese do produto** de configurar por arquivo; (b) qualquer
recurso de segunda tela física é **Desktop Mode apenas**. Isto é propriedade do
compositor, não limitação temporária a contornar. → **FM-27**.

### C2. Config por jogo tem duas classes, e uma delas é frágil

| Classe | Emuladores | Efeito de renomear a ROM |
|---|---|---|
| Endereçada por **serial** | DuckStation, PCSX2, Dolphin (`GameSettings/<serial>.ini`) | imune |
| Endereçada por **nome de arquivo** | MesenCE (`GameConfig/<rom>.json`, e `HdPacks/<rom>/`) | **órfã silenciosamente** |

Todo dossiê deve declarar a qual classe seu emulador pertence. → **FM-29**, e
requisito novo para o WI-5: mover o sidecar na mesma transação e no mesmo
rollback.

### C3. Nenhum emulador estudado publica SHA-256

MesenCE, Eden, Ryubing e Citron: nenhum. O único hash machine-readable é o digest
que a API do GitHub expõe por asset — metadado de plataforma, não proveniência
assinada pelo autor.

**Isto precisa virar política declarada no `ADAPTER-MODEL.md`**, não prática
implícita. E há uma classe de risco associada: os assets do Ryubing 1.3.3 foram
**recriados em 2026-03-30** sem mudar a versão — *release imutável que não é
imutável*. Hash pinado antes disso pode não bater.

### C4. Giroscópio como mira absoluta não tem precedente

O gyro-como-mouse do Steam Input é **relativo**; pistola de luz precisa de
**absoluto**. Nenhum precedente publicado de gyro→lightgun. A API libretro expõe
`RETRO_DEVICE_LIGHTGUN` com coordenadas absolutas — é o caminho mais próximo,
mas alimentar isso com giroscópio ninguém fez.

Vale para NES (Zapper), Master System (Light Phaser), PS1 (GunCon), SNES (Super
Scope), Saturn e arcade. **Um spike resolve para todos** — não repetir por
dossiê. Resultado negativo é aceitável; o plano B é trackpad como apontador
absoluto.

## D. Ajustes ao ciclo, para as ondas seguintes

1. **Agrupar por emulador, não só por sistema.** O MesenCE cobre NES, SNES,
   GB/GBC, GBA, PC Engine e Master System/GG. A §2 (adapter), a §3 (BIOS) e boa
   parte da §10 (robustez) do `nes.md` valem para os seis. Estudar SNES logo após
   NES aproveita quase tudo; estudar PS1 no meio quebra o reaproveitamento.
2. **Um bloco de pesquisa por emulador, não por sistema.** O briefing em
   `RESEARCH-BRIEF-FOR-AGENT.md` já foi desenhado assim (bloco A cobre seis
   sistemas). Manter o padrão.
3. **Registrar o que o dossiê errou, não só o que concluiu.** A tabela de
   correções do `STUDY-LEDGER.md` é o artefato que impede o mesmo erro de método
   voltar. Ela é entregável, não penitência.
4. **Fechar `verde` exige licença e manutenção com fonte e data.** Foi o que
   segurou `switch.md` em `revisão` por um dia — corretamente.

## E. Estado em 2026-07-25

- `switch` — **verde**. WI-S0 proposto com cinco entregáveis concretos.
- `nes` — **verde**. WI-N1 proposto. Riscos abertos declarados: gyro sem
  precedente, HD Packs sem verificação em Linux, netplay sem documentação.
- FM propostos: **27**, **28**, **29**. Próximo disponível: **FM-30**.
- Próximo da fila: **`snes`** — pela lógica de agrupamento do item D1.
