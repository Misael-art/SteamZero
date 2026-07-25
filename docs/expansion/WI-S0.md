# WI-S0 — Proveniência dos adapters de Switch

Prompt fechado para o agente implementador. Copie tudo abaixo da linha.
A validação será feita por outro agente, que **reexecuta tudo** — ver §Validação.

Origem: `docs/emulators/switch.md` §14, a partir da coleta de 2026-07-25.

---

## Seu papel

Você implementa **um único item de trabalho**, autocontido. Não é estudo, não é
refatoração, não é oportunidade de melhorar o que estiver por perto.

Leia antes de tocar em qualquer arquivo: `AGENTS.md` na raiz,
`docs/03-architecture/ADAPTER-MODEL.md`, `docs/emulators/switch.md`.

## Regras que invalidam a entrega se quebradas

1. **Branch própria**, criada a partir do tip que o operador indicar. Nunca
   commite em branch alheia. Não faça push sem autorização explícita.
2. **Zero instalação no host.** Este WI não instala, não ativa, não reverte
   release, não usa `sudo` nem `bigsudo`, não toca `/opt`, `/etc`, `/usr/local`
   ou `/boot`. Baixar artefato para calcular hash é permitido; instalar não.
3. **Gates após cada item**, não só no fim:
   `.venv/bin/pytest tests -q` · `.venv/bin/ruff check src tools tests` ·
   `.venv/bin/ruff format --check src tools tests` · `.venv/bin/mypy src` ·
   `make independence boundaries`. Cobertura não regride.
4. **Não enfraqueça nem delete teste para passar.** Se um contrato mudou de
   verdade, documente no commit qual e por quê.
5. **Independência (ADR-0019).** Nenhuma referência a projetos de pesquisa em
   código, string de UI, path ou marcador.
6. **Não invente hash.** Todo SHA-256 que você escrever tem de ter sido
   calculado por você, a partir do arquivo baixado, com o comando registrado no
   relatório. Um hash plausível que não confere quebra a instalação no host de
   um jeito difícil de diagnosticar.

## Contexto: o que está errado hoje

Três manifestos em `src/steamzero/adapters/manifests/` descrevem emuladores de
Switch. A coleta de 2026-07-25 apurou o seguinte (fatos, com fonte):

| Problema | Evidência | Fonte |
|---|---|---|
| `citron.adapter.json` **não declara `license`** — `eden` e `ryubing` declaram | leitura do manifesto | repo |
| O Citron tem **canal estável**, e nós pinamos a **nightly**. A release `2026-04-17` publicou assets `citron_stable-*`; a `2026-04-27`, que pinamos, publicou só `citron_nightly-*` | releases do projeto | https://github.com/citron-neo/emulator/releases/tag/2026-04-17 |
| A licença do Citron **é GPL-3.0** | campo de licença do repositório | https://api.github.com/repos/citron-neo/emulator |
| Os assets do **Ryubing 1.3.3 foram recriados em 2026-03-30** (migração GitLab→Forgejo) sem mudar a versão. O SHA-256 que pinamos pode estar obsoleto | timestamps dos assets | https://git.ryujinx.app/projects/Ryubing/releases/tag/1.3.3 |
| **Nenhum** dos três projetos publica SHA-256 | busca por `SHA256SUMS`, `checksums.txt` e variantes — todas 404 | coleta 2026-07-25 |

## Entregáveis

Faça **nesta ordem**, com gates entre cada um, e um commit por item.

### S0-1 — Declarar a licença do Citron

Adicionar `"license": "GPL-3.0"` a `citron.adapter.json`, no mesmo lugar
estrutural em que `eden` e `ryubing` a declaram.

⚠️ **Isto muda o `manifestHash`.** O hash é calculado sobre a forma canônica do
manifesto (`src/steamzero/adapters/registry.py:181`) e está travado em
`src/steamzero/adapters/component-lock.json`. Você **precisa** regenerar a
entrada do lock. Descubra como o repo faz isso — não edite o hash à mão sem
entender de onde ele vem. `tests/integration/test_adapters.py` cobre o lock.

### S0-2 — Repinar o Citron no canal estável

Trocar a fonte da nightly `2026-04-27` para o asset **estável** da release
`2026-04-17`: `citron_stable-*` AppImage `x86_64`.

- Escolha entre `x86_64` e `x86_64_v3` e **justifique no relatório**. O alvo é
  Steam Deck (Zen 2); diga por que a sua escolha é a certa para esse alvo.
- Baixe o arquivo, calcule o SHA-256, e registre o comando e a saída.
- Atualize `version`, `url` e `sha256` no manifesto **e** no lock.
- O arquivo baixado **não entra no commit**. Se aparecer em `dist/` ou em
  qualquer lugar do diff, remova.

### S0-3 — Reconferir o SHA-256 do Ryubing 1.3.3

Baixar `ryujinx-1.3.3-x64.AppImage` da URL já pinada e comparar com o
`sha256` do manifesto (`b4511f46…`).

- **Se conferir:** não mude nada. Registre no relatório que conferiu, com a
  saída do comando. *Confirmar que está certo é entregável.*
- **Se divergir:** atualize manifesto e lock com o hash real e **destaque isso
  no relatório** — significa que o artefato mudou sob uma versão que deveria ser
  imutável, e é a informação mais importante que este WI pode produzir.

### S0-4 — Conferir o Eden

Confirmar que a `v0.2.1` PGO para Steam Deck ainda é a corrente e que a URL
pinada responde. Mesmo tratamento do S0-3: se o hash conferir, registre; se não,
corrija e destaque.

### S0-5 — Declarar a política de hash calculado localmente

Nenhum dos emuladores publica SHA-256. Hoje isso é prática implícita; passa a
ser política escrita.

Acrescentar a `docs/03-architecture/ADAPTER-MODEL.md`, na seção de regras, um
item curto declarando que: quando o upstream não publica hash, o SHA-256 é
calculado no primeiro download e fixado no manifesto; a origem do hash é
registrada; e divergência posterior é **falha de verificação**, nunca motivo
para atualizar o pin silenciosamente.

Texto seu, no tom do documento. Não copie o meu fraseado.

## O que NÃO fazer

- Não adicione, remova ou renomeie adapters.
- Não mexa em `dolphin`, `duckstation` ou `retroarch`.
- Não altere o schema de `adapter-v1` nem o enum de capacidades — a `ADR-0021`
  decidiu mantê-lo fechado.
- Não implemente nada de NES/MesenCE. Aquilo depende do WI-R0, que não existe.
- Não "aproveite para" corrigir outra coisa que notar. Registre no relatório e
  siga.
- Não toque em `docs/WORKLOG.md` durante o trabalho; ao final, **acrescente**
  sua própria sessão, sem editar as anteriores.

## Relatório final obrigatório

Sem isto a entrega não é avaliável:

1. **Tabela item → commit → evidência.** Uma linha por entregável S0-1..S0-5.
2. **Para cada hash:** o comando exato que você rodou e a saída completa.
   Diga se conferiu ou divergiu.
3. **Justificativa da escolha `x86_64` × `x86_64_v3`** (S0-2).
4. **Como você regenerou o `component-lock.json`** — comando ou procedimento.
5. **Saída literal dos cinco gates**, colada, não parafraseada. Não escreva
   "gates verdes"; cole o que o terminal imprimiu.
6. **O que ficou fora de escopo** e por quê.
7. **O que você não conseguiu fazer.** Esta seção vazia é suspeita.

## Validação

Um agente supervisor vai **reexecutar tudo** — não confie em declaração.
Especificamente, ele vai:

- rodar os cinco gates do zero no seu commit;
- **rebaixar cada SHA-256** do manifesto contra o arquivo servido na URL;
- verificar que o `component-lock.json` bate com o `manifestHash` recalculado a
  partir dos manifestos;
- conferir que nenhum artefato baixado entrou no diff;
- conferir que `dolphin`, `duckstation` e `retroarch` não foram tocados;
- ler os testes que você citar como prova e confirmar que exercitam produção.

**Precedente que motiva esse rigor:** neste repositório um agente já declarou
"Gates: ruff" numa mensagem de commit enquanto `ruff check` falhava com dois
erros no arquivo de teste que o próprio commit criara. Declaração não é
evidência. Cole a saída.

Uma entrega com S0-3 dizendo "divergiu, aqui está o hash novo e a prova" é
melhor que uma dizendo "tudo certo" sem a saída do comando.
