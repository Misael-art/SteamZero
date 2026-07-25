# WI-S0 — Fundação pura do compartilhamento de tela

Decisão de arquitetura: `docs/adr/0022-compartilhamento-de-tela-multi-provedor.md`.

## Entrega

- `ScreenCastProviderPort` e DTOs neutros (`CastCapabilities`, `ReceiverDescriptor`,
  `LinkSample`, `CaptureConsent`) na camada de portas: as quatro vias entram sem
  tocar domínio nem UI;
- `domain.screencast` puro: resolução de capacidade, seleção de um toque com cadeia
  de fallback, negociação, máquina de estados, escada de degradação, planos de
  recuperação por falha e backoff de reconexão;
- contrato público `screen-cast-v1` para estado de sessão;
- oito códigos de erro `E-CAST-*` com texto acionável em pt-BR;
- nenhuma via implementada ainda: este WI é a fundação que as vias compartilham.

## Robustez e resiliência

- **Sem beco sem saída:** todo estado tem saída declarada e alcança `idle`;
  `streaming`, `degraded` e `recovering` não têm atalho para `idle` — o desligamento
  passa por `stopping` para revogar a captura em ordem (P8);
- **Qualidade antes da sessão:** bitrate (−25% até o piso do perfil) → resolução
  (1440p → 1080p → 720p → 540p) → quadros (60 → 30). No piso, a decisão reporta
  `exhausted` e devolve a escolha à máquina de estados em vez de derrubar o enlace;
- **Recuperação sem encerrar:** perda de encoder reconstrói e retoma; troca de
  resolução renegocia; troca de dispositivo de áudio reinicia só o áudio e
  ressincroniza o relógio; jogo encerrado volta a fonte para o launcher;
- **Reconexão progressiva:** 0, 1, 2, 4 e 8 s; esgotada, falha com `E-CAST-LINK-LOST`
  e causa registrada;
- **Recuperação da qualidade:** enlace estável sobe o bitrate em degraus até o teto do
  perfil, nunca acima do que foi negociado.

## Honestidade de capacidade

- compatibilidade vem de capacidade observada; marca, modelo e ano não entram no
  modelo — não existe caminho no código que os leia;
- receptor sem evidência sai com `supported_modes` vazio e motivo concreto
  (`receiver-app-required`, `codec-unavailable`, `capabilities-unknown`,
  `no-supported-mode`, `protocol-unknown`), que a UI transforma em ação;
- negociação só rebaixa: teto é o menor valor observado entre os dois lados;
- H.264 e Opus são piso; outro codec só é escolhido quando o piso não existe nos dois
  lados; sem interseção, `E-CAST-RECEIVER-INCOMPATIBLE`;
- retorno de entrada só é ativado quando o receptor comprovou o canal.

## Segurança e privacidade

- sem autorização do portal não há sessão, e o escopo concedido precisa cobrir o modo
  (janela não autoriza espelhar a tela inteira);
- revogação de consentimento para a sessão e não se recupera sozinha;
- conteúdo protegido pausa o envio e explica; nenhum caminho de contorno de HDCP/DRM;
- `screen-cast-v1` proíbe por construção (`additionalProperties: false`) nome,
  endereço e PIN; a identidade publicada é digest de 12 hex do id do receptor;
- modo mídia não pede autorização de captura porque não captura a tela.

## Evidência

- suíte integral: 1.518 testes aprovados;
- `tests/unit/test_screencast.py`: 42 testes, cobertura do domínio novo em 100%;
- cobertura total 85,62% (linha anterior 85,32%, sem regressão);
- Ruff (check e format), mypy em 156 módulos, independência e fronteiras: aprovados;
- contratos golden incluem `screen-cast-v1.schema.json`;
- testes provam alcançabilidade de `idle` a partir de todo estado, ausência de atalho
  `streaming → idle`, escada completa de degradação até o piso, plano para toda falha
  declarada, e ausência de nome/endereço/id no contrato público.

Estado final: `verified-dev`. Nenhuma ação de host executada.

## Próximos WIs

| WI | Escopo |
|---|---|
| S1 | Via `game-stream`: componente reversível do motor, preflight, descoberta local, pareamento por PIN/QR e sessão de ponta a ponta |
| S2 | Motor fora do processo da UI, comandos idempotentes e sessão que sobrevive ao restart da interface |
| S3 | UI de um toque navegável por gamepad, cartões de dispositivo com capacidade honesta e overlay durante o jogo |
| S4 | Via `steam-remote-play` |
| S5 | Via `screen-mirror` (compatibilidade com TV sem aplicativo receptor) |
| S6 | Via `media-cast` (trailers, vídeos e músicas) |
| S7 | Retorno de gamepad e monitor virtual (jogo na TV sem espelhar dados pessoais) |
