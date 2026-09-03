# Tela do catálogo de temas — 2026-09-03

Fecha a lacuna `GAP-THEME-ESDE-NO-SCREEN`: as rotas do catálogo passaram a ter
uma superfície que as consome. Antes disto o recurso funcionava e **não existia
para o usuário**.

## Capturas

| Arquivo | O que mostra |
|---|---|
| `01-catalogo.png` | Os cinco temas curados, cada um com licença e cadeia de crédito. Store vazio. |
| `02-instalado.png` | XMB Menu instalado: selo, `Reinstalar`/`Remover`, store em 66,1 MB / 474 arquivos. |
| `03-remocao-preserva.png` | Depois de remover: o tema volta a `Instalar` e **os 474 arquivos continuam no disco**. |
| `04-espaco-recuperado.png` | Depois de pedir a recuperação: store em 0 B, e o contador de órfãos some. |

O par 03/04 é o ponto do desenho: remover um tema **não** apaga arte, porque
outro tema pode usá-la. A recuperação é uma ação separada e pedida.

## Dois defeitos que a captura pegou

Ambos meus, e ambos do tipo que só aparece quando se olha o resultado.

**A terceira captura chamava-se `03-espaco-recuperado` exibindo o espaço ainda
por recuperar.** O nome afirmava um estado que a tela não mostrava — o mesmo
defeito de um erro que anuncia a causa errada. Renomeada para
`03-remocao-preserva`, que é o que ela de fato prova.

**A quarta captura era de um estado impossível.** Eu montava `gcPreview` à mão
para simular o pós-recuperação, e o resultado mostrava a tela oferecendo
recuperar 66,1 MB que já haviam sido recuperados. O painel nunca produz isso:
`applyGarbage()` limpa o `gcPreview`. A captura agora **chama a função real** em
vez de escrever o estado final, então o que aparece é o que o código gera.

Fabricar o estado final teria produzido uma evidência bonita de algo que não
acontece.

## Verificação

`tests/qml/check_theme_catalog_panel.qml` — **12 testes com clique real** via
`qmltestrunner` do Qt 6.11.1, todos passando. O harness aciona o botão e observa
a CHAMADA que sai do painel; conferir que um botão existe provaria que alguém o
desenhou, não que ele age.

Cobrem, entre outros: o botão de instalar chamar a rota de verdade; reinstalar
enviar `overwrite`; remover exigir confirmação antes de chamar; a coleta ter
prévia antes de apagar; `instalado` e `desatualizado` serem estados distintos;
falha de catálogo permanecer na tela em vez de sumir.

`tests/integration/test_theme_catalog_panel_gestures.py` — 4 testes, incluindo a
guarda de código que impede um vermelho de ser "consertado" trocando o clique
real por uma chamada direta ao handler.

## O que esta evidência NÃO prova

- **As capturas vêm de um duplo local, não do host.** A tela é real e o código é
  o de produção, mas os dados são de um dublê: ligar a captura à rede a tornaria
  dependente de um download e do estado do host. O ciclo contra o host real está
  em `2026-09-03-esde-catalogo-host/`.
- **Nenhuma cena ES-DE foi renderizada.** Instalar um tema ainda não muda a
  aparência da central — `activated: false` é deliberado. `GAP-THEME-ESDE-SCENE-NOT-RENDERED`
  continua aberta.
- Nada foi medido em desempenho, FPS ou memória.

## Reprodução

```bash
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qml tests/qml/capture_theme_catalog.qml \
  -- --output-dir=docs/09-operations/evidence/2026-09-03-tela-temas
/usr/lib/qt6/bin/qmltestrunner -input tests/qml/check_theme_catalog_panel.qml
```
