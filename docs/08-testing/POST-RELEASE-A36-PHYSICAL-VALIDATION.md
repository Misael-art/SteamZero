# Validação física pós-release 0.1.0a36

Data: 2026-07-26  
Branch de correção: `codex/post-release-validation-hygiene`  
Host: KDE Plasma 6.6.6, Wayland, 1280×800

## Resultado

| Item | Resultado | Evidência |
|---|---|---|
| Portal KDE — monitor | aprovado | `CreateSession`, `SelectSources`, `Start` e `OpenPipeWireRemote`; FD 9 e node 91/123 retornados |
| Portal KDE — janela | aprovado | seletor exibiu ChatGPT, OpenCode e Edge; seleção retornou FD 9 e node 128 |
| Quadros reais | aprovado | PipeWire negociou, WebRTC criou offer/answer e o Edge exibiu os quadros do monitor |
| Encerramento pelo aplicativo | aprovado | pipeline, sessão, FD, subscription, processo e socket foram encerrados sem processo residual |
| Revogação pelo compositor | pendente | o seletor KDE deste host não oferece um controle persistente de revogação acessível; o contrato `Session.Closed → CAPTURE_REVOKED` tem cobertura automatizada, mas ainda precisa de teste físico em um compositor que exponha “Parar compartilhamento” |
| UI 1280×800 | aprovado em offscreen | sete seções foram capturadas sem warning QML, clipping ou sobreposição; Transmissão e Sistema foram inspecionadas separadamente |
| P2P pela internet | não implementado | WI-S1 usa HTTP/SSE em `127.0.0.1` e `iceServers: []`; o trabalho seguro está especificado em `WI-S2.md` |

## Defeitos encontrados e corrigidos

1. o caminho de request D-Bus preservava `:` e era inválido;
2. a mesclagem de `a{sv}` desmontava os valores `GLib.Variant`;
3. a inscrição em `Request.Response` filtrava um sender incompatível com o backend KDE;
4. o motor não chamava `Gst.init(None)` e terminava com `SIGSEGV`;
5. o pipeline fixava 30 fps antes de `videorate`, causando `no more input formats`;
6. `GstWebRTC` não era carregado antes de ler a offer, produzindo `GBoxed`;
7. a fase `streaming` era publicada antes de a answer remota ser aplicada;
8. o stderr do motor era descartado, ocultando todos os diagnósticos acima.

## Limites da evidência

Esta validação foi executada a partir da árvore da branch, não da release instalada
no host. Nenhuma instalação, rollback, wheel ou wheelhouse foi produzido. A
release publicada continua sendo a `0.1.0a36`, e o host continua na release que
já estava ativa antes desta sessão.
