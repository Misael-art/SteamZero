# BRIEFING DE PESQUISA — agente coletor de fatos para dossiês de emulador

Copie tudo abaixo da linha para o agente. Ele devolve **um único arquivo
Markdown**; eu o converto em dossiês.

---

## Quem você é e o que NÃO deve fazer

Você é um **coletor de fatos verificáveis**. Não é arquiteto, não decide nada,
não escreve código, não baixa nem compila nada.

**Regras que invalidam a entrega se quebradas:**

1. **Todo fato carrega URL + data de consulta.** Sem fonte, não é fato — é
   hipótese, e vai marcado `[hipótese]`.
2. **Nunca preencha uma lacuna com conhecimento de treino.** Se não achou,
   escreva `NÃO ENCONTRADO` e diga onde procurou. Uma lacuna honesta vale mais
   que um preenchimento plausível — quem recebe isto vai pinar SHA-256 e
   instalar num host real a partir do que você escrever.
3. **Distinga versão da documentação da versão do binário.** Manual antigo
   descrevendo software novo é a armadilha central desta pesquisa: já
   encontramos documentação oficial de 2020 sendo servida para um binário de
   2026. Sempre registre a data/versão do documento consultado.
4. **Limitação tem o mesmo destaque que recurso.** Se algo não funciona, é
   parcial, ou só funciona em certas condições, isso é entregável de primeira
   classe — não rodapé.
5. **Não pesquise nada que envolva obtenção de BIOS, keys, firmware, ROMs ou
   contorno de DRM.** Se a pergunta parecer levar a isso, responda
   `FORA DE ESCOPO` e siga. Documentar que um sistema *exige* BIOS é ok;
   documentar como obtê-la, não.

Se a busca web falhar no seu ambiente, use um navegador e leia as páginas
diretamente. Registre qual método usou.

## Contexto mínimo (não precisa de mais nada)

Estamos avaliando emuladores para rodar num **Steam Deck** (Linux, 1280×800,
compositor Gamescope em Game Mode e KWin/Wayland em Desktop Mode). Preferimos
emuladores que possam ser **configurados por arquivo**, sem que o usuário abra a
GUI. Pinamos versões por SHA-256.

## Bloco A — prioridade máxima: MesenCE

Um único emulador cobre seis sistemas da nossa fila, então cada fato aqui rende
seis vezes. Repositório: `https://github.com/nesdev-org/MesenCE`.

| # | Pergunta | Formato da resposta |
|---|---|---|
| A1 | Versão estável corrente e data de publicação | versão + data + URL da release |
| A2 | URL exata do artefato **AppImage Linux x86-64** da release estável, e se o projeto publica **SHA-256** desse artefato | URL + sim/não + onde está o hash |
| A3 | Dependências de runtime exigidas no Linux (sabemos de SDL2 — confirme e complete) | lista + fonte |
| A4 | **Onde e em que formato** o MesenCE 2.x grava a configuração (caminho e formato: JSON/INI/XML). Precisamos escrever config por arquivo | caminho + formato + fonte. Se a doc não disser, `NÃO ENCONTRADO` |
| A5 | Existe **configuração por jogo** (override por título)? Como é endereçada — nome de arquivo, hash, serial? | descrição + fonte |
| A6 | A opção "configurar controles automaticamente ao carregar um jogo", baseada na base de dados interna, **existe na linha 2.x**? (Documentamos ela no manual 0.9.9 de 2020 — precisa confirmar que sobreviveu) | sim/não/`NÃO ENCONTRADO` + fonte + **versão do documento** |
| A7 | **Netplay** existe na linha 2.x? Se sim: transporte, lockstep ou rollback, limitações declaradas | descrição + fonte + versão do doc |
| A8 | Quais **periféricos de NES/Famicom** a linha 2.x suporta? Interessam especialmente: Zapper, Four Score, Four Player Adapter, Power Pad, Arkanoid/paddle, microfone do Famicom, Family BASIC keyboard | tabela periférico → suportado sim/não/`NÃO ENCONTRADO` + fonte |
| A9 | **HD Packs** continuam suportados na linha 2.x? Qual o formato e onde ficam? | descrição + fonte + versão do doc |
| A10 | Confirme a limitação de UI sob Gamescope e diga se há **correção ou workaround novo** desde a redação do `SteamOS.md` | estado atual + fonte + data |
| A11 | Para SNES, GB/GBC, GBA, PC Engine, Master System/Game Gear: liste por sistema **um** recurso pouco usado que o MesenCE suporte (ex.: MSU-1, link cable, Super Game Boy) | tabela sistema → recurso → fonte |

## Bloco B — reverificação de proveniência (emuladores de Switch)

Precisamos saber se os projetos estão vivos e sob que licença. **Não pesquise
nada sobre keys/firmware.**

| # | Alvo | Pergunta |
|---|---|---|
| B1 | Eden (`https://git.eden-emu.dev/eden-emu/eden`, pode responder 403 a acesso automatizado — tente navegador) | versão estável corrente; existe build otimizada para Steam Deck?; licença declarada; data do último release/commit |
| B2 | Ryubing (`https://git.ryujinx.app/projects/Ryubing`) | versão estável corrente; licença; data do último release |
| B3 | Citron (`https://github.com/citron-neo/emulator`) | **licença declarada** (é a lacuna que nos bloqueia); existe canal **estável** ou só nightly?; data do último release |
| B4 | Os três | cada um publica **SHA-256** dos artefatos? Onde? |

## Bloco C — restrição de compositor (transversal, alto valor)

Descobrimos que o compositor do Game Mode não renderiza popups de certos
toolkits e não roteia duas janelas para dois monitores. Queremos tratar isso
como restrição de primeira classe.

| # | Pergunta |
|---|---|
| C1 | Estado atual (2026) do suporte de **popups/janelas filhas** no Gamescope: há correção, issue aberta, workaround oficial? URL + data |
| C2 | O Gamescope ganhou suporte **multi-output** ou continua single-output/single-focus? URL + data |
| C3 | Quais emuladores de dois ecrãs oferecem **modo de duas janelas separadas**? Confirme e complete: Cemu (Wii U, GamePad como 2ª janela), Azahar (3DS, "Separate Windows"), melonDS (NDS — nossa informação é que **não tem**; confirme). Para cada um: a opção existe? Qual a chave de configuração em arquivo? |

## Bloco D — giroscópio como pistola de luz (exploratório)

Queremos mapear o giroscópio do Deck para mira de pistola de luz (Zapper,
GunCon, Super Scope). Não achamos precedente.

| # | Pergunta |
|---|---|
| D1 | Existe **precedente documentado** de alguém mapeando giroscópio do Steam Deck para pistola de luz em emulador? Se sim: como, com que ferramenta, funcionou? Se não: diga `NÃO ENCONTRADO` |
| D2 | Quais emuladores expõem a pistola de luz como **eixo absoluto de mira** (mapeável a um dispositivo apontador) em vez de exigir mouse? |
| D3 | O Steam Input expõe o giroscópio como **mouse** para aplicações não-Steam? Documentação oficial + data |

## Formato exato da entrega

Um arquivo Markdown com esta estrutura, sem prosa introdutória:

```markdown
# Coleta — <data> — método: <busca web | navegador | ambos>

## Bloco A — MesenCE
### A1
**Resposta:** <fato objetivo>
**Fonte:** <URL>
**Consultado:** <AAAA-MM-DD>
**Versão do documento:** <versão/data do doc, ou "não declarada">
**Confiança:** fato | [hipótese] | NÃO ENCONTRADO
**Notas:** <limitações, contradições entre fontes, o que procurou se não achou>

### A2
...
```

Repita para todos os itens de A a D. **Um item por seção, sem agrupar.**

Ao final, uma seção obrigatória:

```markdown
## Contradições e alertas
<Qualquer lugar onde duas fontes discordaram, onde a documentação parecia
desatualizada em relação ao binário, ou onde você suspeita que a resposta
mudará em breve. Se não houver nada, escreva "nenhuma".>

## O que eu não consegui responder e por quê
<Lista honesta. Esta seção vazia é suspeita.>
```

## Critério de aceite

A entrega é aceita quando: todo item de A a D tem seção própria; nenhum fato
está sem URL e data; toda resposta baseada em documentação declara a versão do
documento; as duas seções finais estão preenchidas de verdade. Uma entrega com
`NÃO ENCONTRADO` honesto em metade dos itens é melhor que uma entrega completa
com um único fato inventado.
