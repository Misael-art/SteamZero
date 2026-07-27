# 1. Visão, escopo e princípios

## 1.1 Objetivo

Permitir que a central Qt/QML do SteamZero:

- ofereça temas nativos mais refinados sem espalhar cores e medidas pelo QML;
- instale e selecione temas de terceiros orientados a dados;
- preserve navegação, acessibilidade, desempenho e verdade operacional;
- volte ao tema padrão quando um pacote falhar, desaparecer ou se tornar incompatível.

O framework é uma camada visual sobre os contratos existentes. Ele não cria um novo
launcher, serviço, banco de biblioteca, barramento de eventos ou runtime gráfico.

## 1.2 Estado atual observado

- `src/steamzero/ui/qml/Main.qml` concentra os tokens principais de cor.
- Componentes filhos recebem parte das cores por `required property`, mas ainda há
  valores hexadecimais locais em vários arquivos.
- Alto contraste e redução de movimento já chegam em
  `dashboard.accessibility`.
- A central é iniciada por `launch_desktop_ui()` e consome uma bridge HTTP
  loopback autenticada.
- QML é opcional: backend e CLI continuam funcionais sem o runtime Qt.
- Há harnesses offscreen, inclusive para alto contraste e layouts compactos.

O plano deve evoluir esses pontos, não substituí-los.

## 1.3 Escopo do primeiro marco

Incluído:

- contrato `theme-manifest-v1`;
- tema padrão nativo e um segundo tema nativo de referência;
- catálogo local de temas válidos;
- instalação, preview, ativação e remoção de pacote externo;
- tokens de cor, tipografia, geometria, densidade, movimento e assets;
- fallback seguro;
- painel de temas navegável por controle;
- testes unitários, de integração, segurança e QML offscreen.

Fora de escopo:

- marketplace, download remoto e contas;
- editor visual;
- sincronização de temas;
- QML/JavaScript/shaders de terceiros;
- plugins ou chamadas ao sistema operacional;
- troca da tecnologia de Game Mode;
- áudio, vídeo ou fontes baixadas automaticamente;
- compatibilidade visual com outros produtos.

## 1.4 Princípios

1. **Um contrato, duas origens.** Temas nativos e externos obedecem ao mesmo esquema.
2. **Sem código de terceiros.** O pacote descreve aparência; não executa comportamento.
3. **Tokens semânticos.** Componentes pedem `text.primary`, `surface.raised` e
   `status.warning`, não cores específicas.
4. **Preferência não supera acessibilidade.** Alto contraste, redução de movimento e
   escala do host têm precedência.
5. **Preview não persiste.** Só `apply` confirmado altera a preferência.
6. **Fallback sempre disponível.** O tema padrão é empacotado e não pode ser removido.
7. **Offline primeiro.** Instalar de um diretório ou arquivo local é suficiente.
8. **Falha degrada.** Tema inválido é rejeitado ou desativado; a UI continua abrindo.
9. **Controle primeiro.** Seleção, preview, aplicar, cancelar e remover funcionam sem mouse.
10. **Sem segunda fonte de verdade.** QML só renderiza o read model produzido pelo backend.

## 1.5 Perfis de experiência

O mesmo tema deve suportar:

- portátil/compacto;
- monitor Desktop;
- TV/10-foot quando a UI Qt for usada;
- alto contraste;
- movimento reduzido.

Um pacote pode oferecer valores específicos por perfil apenas nos campos previstos pelo
esquema. Não pode escolher rotas, esconder ações críticas ou alterar a semântica do foco.
