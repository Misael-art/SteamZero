# ADR-0022 — Compartilhamento de tela como plataforma multi-provedor com plano de mídia delegado

**Status:** aceito

## Contexto

O operador especificou "compartilhar tela com um toque" com foco em experiência,
robustez e resiliência, e determinou que **todas as vias sejam construídas, começando
pela estratégia de motor de baixa latência já existente** (host Sunshine + clientes
Moonlight). A especificação original descreve quatro vias (espelhamento Miracast,
protocolo próprio de jogo sobre WebRTC, Google Cast de mídia e AirPlay), emissores em
Windows 11 e Steam Deck, e aplicativos receptores próprios para Android TV e tvOS.

Três fatos do produto restringem o desenho:

1. **NON-GOAL N5** mantém o produto Linux-first: não há suporte a Windows, macOS ou
   Android como plataforma do SteamZero. Escrever um emissor Windows ou publicar um
   app receptor Android/tvOS não é escopo do v1.
2. **B0 (`backlog-protected`)** cobre "Web UI LAN, família/kiosk, comunidade,
   pareamento". Qualquer superfície de rede aqui precisa ficar estritamente dentro do
   compartilhamento de tela, sem abrir a Web UI nem funções de comunidade.
3. Escrever uma pilha WebRTC própria (sinalização, ICE, congestionamento, FEC,
   retransmissão) mais um receptor nativo por plataforma é trabalho de anos e não é a
   parte do problema em que este produto se diferencia.

A sondagem do host alvo (Steam Deck com BigLinux/KDE em Wayland) confirmou o que a
via principal precisa: portal do KDE com `ScreenCast` e `RemoteDesktop`, PipeWire, e
encoder por hardware VA-API para H.264 e HEVC.

## Decisão

1. **Uma função de produto, várias vias.** O usuário vê "Transmitir para a TV". Cada
   via é um provedor por trás da porta `ScreenCastProviderPort` (`steamzero.ports`):
   `game-stream`, `steam-remote-play`, `screen-mirror` e `media-cast`. Ids internos
   descrevem a tecnologia; o nome de produto na UI é decidido separadamente e não vaza
   para contrato, log ou schema.
2. **A decisão é nossa; o plano de mídia é delegado.** `domain.screencast` é puro e
   decide capacidade, alvo, modo, negociação, degradação, reconexão e recuperação. Ele
   não captura, não codifica e não fala com a rede. O SteamZero **não** escreve pilha
   WebRTC, protocolo de transporte nem codec próprio.
3. **A primeira via é um motor existente de baixa latência** (host Sunshine, clientes
   Moonlight): licença GPL-3 compatível com este repositório, encoder por hardware,
   retorno de gamepad, bitrate adaptativo e clientes já publicados para Android TV,
   Apple TV, webOS, Tizen, desktop e navegador. Não construímos aplicativo receptor.
4. **O motor é componente reversível, não dependência oculta.** Ele é instalado sob o
   modelo de componentes do repositório, com preflight próprio. Motor ausente produz
   `E-CAST-ENGINE-MISSING` com ação concreta na UI — nunca falha silenciosa nem
   instalação automática sem consentimento.
5. **Ordem de construção das vias:** `game-stream` (jogo, baixa latência) →
   `steam-remote-play` (atrito zero onde o Steam já resolve) → `screen-mirror`
   (compatibilidade com TV sem aplicativo receptor) → `media-cast` (trailers, vídeos e
   músicas). Todas atrás da mesma porta, sem lógica de protocolo na UI.
6. **Compatibilidade vem de capacidade observada.** Marca, modelo e ano do receptor
   não são evidência e não entram no modelo. Receptor sem evidência sai da resolução
   com `supported_modes` vazio e um motivo concreto (`receiver-app-required`,
   `codec-unavailable`, `capabilities-unknown`, `no-supported-mode`,
   `protocol-unknown`). H.264 e Opus são piso negociado; HEVC e AV1 são negociados,
   nunca presumidos.
7. **A qualidade cai antes da sessão** (P8). A escada reduz bitrate, depois resolução,
   depois quadros; no piso ela reporta esgotamento em vez de derrubar o enlace. Perda
   de encoder, troca de resolução e troca de dispositivo de áudio recuperam sem
   encerrar a sessão. Reconexão é progressiva (0, 1, 2, 4, 8 s) e falha com causa
   registrada.
8. **O motor roda fora do processo da UI.** Reiniciar a interface não derruba a
   sessão; o motor cair não derruba o launcher.
9. **Privacidade por construção.** Não existe captura sem autorização explícita do
   portal, e o escopo autorizado precisa cobrir o modo pedido. O contrato público
   `screen-cast-v1` não admite nome, endereço ou PIN do receptor: a identidade é um
   digest de 12 hex. Conteúdo protegido pausa o envio e explica; nunca é contornado.
   Acesso remoto não é oferecido; o alcance é a rede local.
10. **Emissor permanece Linux/Wayland; N5 e B0 seguem intactos.** As partes da
    especificação sobre emissores Windows/macOS e receptores próprios ficam registradas
    como referência de arquitetura futura, não como escopo. O pareamento local desta
    função não abre a Web UI LAN nem funções de comunidade de B0.

## Consequências

O produto ganha, na primeira via, um plano de mídia maduro (codec, adaptação,
retransmissão, clientes multiplataforma) e concentra o esforço onde o valor é nosso:
seleção de um toque, capacidade honesta, degradação previsível e recuperação sem
tela preta. As vias seguintes entram sem reescrever a UI nem o domínio, porque a
decisão já está isolada atrás de uma porta.

O custo é uma dependência externa com versão e superfície próprias. Isso é mitigado
por preflight explícito, capacidade sempre observada em vez de presumida, e queda de
modo quando a via preferida não está disponível. Em troca, a telemetria fina fica
limitada ao que o motor expõe — aceitável frente ao risco de manter uma pilha de
transporte própria.
