# RISK-REGISTER — registro de riscos

Prob./Impacto 1–5. Responsável: papel (a nomear na aprovação — Q6/equipe).

| ID | Risco | P | I | Exposição | Mitigação | Gatilho de revisão | Responsável |
|---|---|---|---|---|---|---|---|
| R-01 | Q2 não decidida ⇒ reuso ilegal ou paralisia | 3 | 5 | 15 | bloqueio operativo (LICENSE-MATRIX): zero cópia até ADR-0013; fundação captura comportamento para permitir reimplementação | início da Fase 1 | Product owner |
| R-02 | Escopo inflar (boot/VM/homelab, multi-user, plugins) | 4 | 4 | 16 | NON-GOALS assinados; mudança de escopo só por ADR | todo planning | Gerente técnico |
| R-03 | Atualização SteamOS/Steam Client quebra integrações (Steam Input, gamescope, QAM) | 5 | 3 | 15 | Compat Matrix + modo degradado explícito (FM-10); núcleo independente de Decky; testes por canal beta da Valve | cada SteamOS beta | Eng. plataforma |
| R-04 | Godot inadequado p/ acessibilidade/entrada (G10) | 3 | 4 | 12 | ADR-0002 exige protótipo com critérios mensuráveis ANTES da Fase 5; plano B: Qt/QML | fim da Fase 1 | Eng. UI |
| R-05 | Sem hardware para a matriz (Q6) ⇒ release "verified-vm" apenas | 3 | 4 | 12 | inventário de dispositivos na aprovação; comunidade beta para cobertura | Fase 2 | Product owner |
| R-06 | Upstreams de emuladores mudam licença/distribuição (caso DuckStation) | 4 | 3 | 12 | licença por manifesto verificada por release; lockfile permite congelar última versão OK | Fase 4, contínuo | Legal/Eng. |
| R-07 | Cloud sync corrompe saves (pior dano possível de reputação) | 2 | 5 | 10 | timeline preservadora (GA-05), conflitos nunca auto-resolvidos, RT-09/10, feature atrás de flag até M9 | Fase 3 | Eng. dados |
| R-08 | Complexidade do núcleo transacional atrasa tudo (over-engineering) | 3 | 4 | 12 | Fase 1 enxuta com critérios de saída objetivos (M1–M3); pipeline mínimo primeiro, sagas depois | review M1 | Arquiteto |
| R-09 | Performance do scan/hash em bibliotecas 10k+ no Deck | 3 | 3 | 9 | incremental por mtime+size com re-hash amostral; benchmark funcional presente (tempo publicado via JUnit, não como gate absoluto) | Fase 3 | Eng. |
| R-10 | Flatpak sandbox inviabiliza operações (portais insuficientes p/ helper/mounts) | 2 | 4 | 8 | ADR-0003 híbrido já prevê helper host; spike técnico no início da Fase 6 | Fase 2 spike | Eng. plataforma |
| R-11 | Concorrência dupla-gestão (usuário mantém EmuDeck/RetroDECK ativos) corrompe estado | 4 | 3 | 12 | drift detection por verify, avisos de dupla-gestão nos imports | Fase 5 | Eng. |
| R-12 | Fadiga documental: docs divergem do código na implementação | 4 | 3 | 12 | contratos como golden files executáveis; ADR obrigatório para desvio; docs no DoD | contínuo | Todos |
| R-13 | Dependência de projetos de referência para comportamento (repos podem sumir) | 2 | 2 | 4 | clones de referência preservados localmente; comportamento capturado nesta fundação | — | — |
| R-14 | RetroDECK/components não clonado (G1) esconde detalhes do modelo | 2 | 2 | 4 | clone sparse antes da Fase 4 | Fase 4 kickoff | Eng. |
| R-15 | Nome "SteamZero" contém "Steam" (marca da Valve) — risco de confusão de afiliação ou objeção de marca | 2 | 3 | 6 | disclaimer "não afiliado à Valve" em README/UI "Sobre"; evitar logo/trade dress da Valve; validar diretrizes de marca da Valve antes do release público; plano B de renome barato (nome só em i18n/constantes) | antes do primeiro release público (Fase 6) | Product owner |
