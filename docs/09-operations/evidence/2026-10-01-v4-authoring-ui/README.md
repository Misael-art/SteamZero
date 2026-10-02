# Edição e execução de tema: prova local e roteiro B_VISUAL

## O que esta rodada prova

O teste `tests/integration/test_theme_authoring_e2e.py` abre o `ThemeEditorPanel`
real em um harness QML e envia `mouseClick`/`keyClick` aos controles visíveis. A
ponte usa um `DesktopControlServer`, `DesktopDashboard`, `ThemeEditorManager` e
`ThemeBridge` reais; os dados e a configuração ficam em `XDG_DATA_HOME` e
`XDG_CONFIG_HOME` temporários. O renderer testado é o caminho da **AURA UI**:
`EditorialLibrary` → `MediaEffectLayer`, alimentado pelo `/status` publicado
depois da aplicação explícita do tema.

A biblioteca contém somente um registro sintético e a imagem PNG CC0 de
`tests/fixtures/themes/esde-mini/fundo.png`. Nenhuma biblioteca ou preferência
pessoal é lida pelo teste. A execução usa Qt 6.11.2, plataforma `offscreen` e
renderer software. É uma prova de UI QML e pixels no checkout, não de input
físico, release instalada, sessão gráfica real ou AT-SPI.

O ciclo exercitado pela UI é:

1. Duplicar o tema padrão e editar a pilha de mídia: adicionar blur e vinheta,
   mudar `radius=24` e `strength=0.9`, reordenar, escolher o fallback `minimal`;
   abrir o seletor AURA existente, aplicar `#336699` a uma sombra temporária,
   rejeitar `#zz0000` sem alterar documento/histórico e remover essa sombra.
2. Editar movimento: criar o estado nativo `loading` com `scale=1.2`; criar e
   remover uma timeline de rascunho; criar `entrada` como `parallel`, mudar para
   `sequence`, configurar duas repetições, editar estado/duração dos clips,
   movê-los para cima/baixo, rejeitar duração `9999` e remover um clip.
3. Conferir `dirty`, desfazer/refazer, salvar, fechar e reabrir; a declaração
   semântica reaberta deve ser igual à salva.
4. Aplicar o tema explicitamente à central e confirmar pelo `/status` que a
   bridge publicou o ID escolhido. O `MediaEffectLayer` recebe a vinheta salva;
   a imagem aplicada escurece a borda. O teste compara a soma das médias RGB:
   a borda precisa cair mais de 15 pontos e o controle central pode variar menos
   de 12.

Os valores numéricos e as escolhas fechadas vêm de schemas gerados pelas mesmas
regras de domínio que validam efeitos e movimento. Entradas fora de faixa
mostram os limites e voltam ao valor aceito sem criar histórico; uma cor inválida
é recusada pelo domínio e também preserva documento, histórico e seleção.

## Capturas

Todas são capturas do harness QML/software, não fotografias da sessão instalada.
Os arquivos e hashes estão em `SHA256SUMS`.

| Arquivo | Conteúdo |
|---|---|
| `01-studio-efeitos-movimento.png` | Inspetores de efeito e timeline, estado `loading` selecionado e `scale=1.2`; painel 1100×900. |
| `02-studio-compacto.png` | Controles de efeito acessados com a janela 640×560 e coluna rolável. |
| `03-studio-binding.png` | Binding `text ← item.genre` ligado pela UI e exibido no inspetor. |
| `04-studio-compact-movimento.png` | Timeline e clips no viewport 640×560, incluindo seleção de estado e duração. |
| `05-theme-runtime-baseline.png` | Fixture desenhada pelo `MediaEffectLayer` antes de aplicar a vinheta. |
| `06-theme-runtime-aplicado.png` | Mesma mídia depois da aplicação da declaração salva. |
| `07-aura-library-theme-applied.png` | Superfície completa `EditorialLibrary` com fixture sintética e tema ativo. |
| `08-studio-seletor-cor.png` | Diálogo AURA de seleção de cor, aberto pelo controle de sombra. |
| `09-studio-vinheta-editada.png` | Receita final de vinheta visível no inspetor: fallback `minimal`, cor e força `0.9`. |

## Comandos e resultados focados

```bash
rtk .venv/bin/python tools/run_tests_isolated.py tests/unit/test_theme_effect_authoring.py -q
rtk env SZ_CAPTURE_DIR="<diretório-de-evidências>" .venv/bin/python tools/run_tests_isolated.py tests/integration/test_theme_authoring_e2e.py -q
```

Na última execução focada, passaram: 10 testes de autoria de efeitos/movimento
(1,20 s), mais 68 testes de `theme_editor`, `scene_motion` e `theme_effects`
(1,54 s), a jornada QML (14,08 s) e os 2 testes separados de cena importada
(2,20 s). O guard observou o estado real idêntico antes/depois
(`files=12818`, `directories=2068`, `bytes=1372818509`). Essa validação pertence
à árvore de trabalho atual.

No checkpoint integral da árvore congelada desta entrega, `.venv/bin/python
tools/run_tests_isolated.py tests -q` terminou com **6560 passed, 47 skipped em
2302,24 s**. O guard do estado real permaneceu idêntico antes/depois
(`files=12818`, `directories=2068`, `bytes=1372818509`, `max_mtime_ns=1790888510663329431`).
Também passaram `ruff check src tools tests`, `ruff format --check src tools
tests` (689 arquivos), `mypy src` (299 arquivos), `make independence
boundaries`, `make status-check` e `git diff --check`. O checkpoint anterior de
6557/47 continua como histórico, não como resultado desta árvore.

`tests/integration/test_theme_scene_runtime_e2e.py` é uma prova separada:
`SceneEsdeView` decodifica fixtures válidas/licenciadas ES-DE e RetroFE e verifica
pixels. Ela não executa o tema criado nesta jornada. `SceneEsdeView`/Theme Engine,
AURA Launcher e AURA Cinema não são promovidos por capturas da AURA UI.

## Roteiro B_VISUAL para a release autorizada

**Pré-condições:** usar a release construída do SHA completo que será informado
após os gates e o CI; verificar que o manifesto do pacote aponta para o mesmo
`sourceCommit`; registrar release, digest, sessão, resolução e escala. A prova
requer instalação governada autorizada pelo operador. Não instalar nem publicar
esta branch por este roteiro. A release observada antes deste lote era
`2.0.0rc1-5715d7962691`; o rollback preservado era
`2.0.0rc1-e2af2562ebba`. Nenhuma delas contém as mudanças atuais.

Use um perfil de teste isolado e uma mídia sintética licenciada na sessão gráfica
real. Não aponte o teste para a biblioteca Steam pessoal nem ative ações de jogo.
Se a release não oferecer um modo isolado para essa mídia, registre a etapa de
runtime como pendente em vez de alterar a biblioteca pessoal.

1. **Sucesso:** abrir a central instalada; duplicar o tema padrão; no Studio,
   adicionar blur e vinheta, ajustar `24`/`0.9`, escolher `minimal`, abrir o
   seletor AURA, alterar a cor de uma sombra e removê-la. Criar o estado
   `loading`, configurar `scale=1.2`, criar `entrada`, editar tipo/repetição e
   pelo menos dois clips. Navegar pelos controles com mouse e teclado; repetir
   com gamepad quando o foco estiver disponível.
2. **Persistência:** conferir `Não salvo`, desfazer/refazer, salvar, fechar,
   reabrir e comparar os valores. Capturar Studio, seletor de cor, catálogo e
   versão da release.
3. **Execução central:** aplicar explicitamente a cópia à central; observar a
   mídia sintética na `EditorialLibrary` e registrar se a vinheta altera a borda
   da imagem. Restaurar a preferência anterior ou encerrar o perfil temporário.
4. **Erro e recuperação:** inserir um valor numérico acima do limite; confirmar
   mensagem com faixa, valor anterior, seleção e histórico preservados. Digitar
   hexadecimal inválido; confirmar mensagem do domínio e restauração do campo.
   Corrigir, salvar/reabrir e capturar o erro e a recuperação.
5. Registrar input físico e foco. O seletor desta tela é o diálogo AURA existente;
   não declarar um portal nativo testado. Se AT-SPI falhar, registrar a limitação
   do instrumento, sem classificar o produto como reprovado por isso.

**Consumidor desta entrega:** AURA UI central (`EditorialLibrary` /
`MediaEffectLayer`). **Consumidor Engine separado:** `SceneEsdeView`; a ligação
entre um pacote editado e uma cena importada ainda exige uma fatia própria.
Launcher/AURA Cinema não consomem cenas importadas neste recorte. O host atual
permanece na release anterior até existir autorização e instalação governada.
