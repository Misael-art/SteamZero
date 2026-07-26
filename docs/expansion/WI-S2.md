# WI-S2 — Web receiver pela internet

## Estado

Planejado. O WI-S1 é deliberadamente local: servidor em `127.0.0.1`, signaling
HTTP/SSE sem TLS e `RTCPeerConnection` sem STUN/TURN. Expor esse servidor em
`0.0.0.0` não é uma implementação aceitável de acesso remoto.

## Objetivo

Permitir que um receptor autenticado jogue fora da LAN, com conectividade P2P
quando possível e relay TURN quando necessário, sem publicar controle ou mídia
para terceiros.

## Contrato de segurança

- signaling autenticado sobre TLS;
- pareamento de uso único, curto e vinculante ao dispositivo;
- chaves persistentes por dispositivo e revogação imediata;
- STUN configurável e TURN com credenciais efêmeras;
- autorização separada para captura, controle e áudio;
- rate limit, expiração de sessão e proteção contra replay;
- nenhuma mídia, SDP, ICE candidate, segredo ou endereço privado em logs;
- fallback fechado: falha de autenticação, consentimento ou ICE encerra a sessão.

## Entregas

1. definir o modelo de ameaça e escolher o serviço de rendezvous/TURN;
2. adicionar configuração explícita de STUN/TURN e política ICE;
3. implementar signaling remoto autenticado, sem reutilizar o listener loopback;
4. emitir QR/PIN de pareamento de curta duração;
5. autenticar device e sessão antes de aceitar SDP ou candidates;
6. transportar candidates trickle nos dois sentidos e detectar relay;
7. integrar revogação, expiração, reconexão e telemetria sem dados sensíveis;
8. publicar runbook operacional, custos/limites do relay e procedimento de rotação.

## Critérios de aceite

- teste entre duas redes externas independentes, sem port forwarding;
- teste TURN-only com P2P direto bloqueado;
- mídia e input funcionam após troca de candidate e reconexão;
- dispositivo revogado perde signaling, mídia e controle;
- PIN expirado/reutilizado, SDP não autenticado e replay são recusados;
- nenhum listener plaintext ou não autenticado fica exposto;
- quatro gates do repositório verdes e teste físico documentado com origem,
  destino, transporte (`host`, `srflx` ou `relay`) e teardown.

## Decisões ainda necessárias

O operador precisa escolher ou autorizar a infraestrutura de rendezvous e TURN,
o domínio/certificado e o orçamento de relay. Essas decisões envolvem serviço
externo e custo recorrente; não podem ser inferidas do código local.
