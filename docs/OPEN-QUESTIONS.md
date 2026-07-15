# OPEN-QUESTIONS — decisões que pertencem ao responsável pelo projeto

| # | Questão | Contexto | Opções | Impacto se não decidida |
|---|---|---|---|---|
| Q1 | ~~Nome final do produto~~ **RESOLVIDA (2026-07-15): o nome é SteamZero** | Decisão do responsável; binários derivados: CLI `steamzero`, daemon `steamzero-core`, helper `steamzero-admin` | Sub-decisão restante: ID Flatpak (depende de domínio/org de hospedagem, ex.: `io.github.misael-art.SteamZero`) | Atenção de marca: "Steam" é marca da Valve — validar que o nome não sugere afiliação oficial (ver RISK-REGISTER R-15) |
| Q2 | Licença do novo projeto | EmuDeck/LinuxToys/RetroDECK são GPL-3.0; PhaseZero não tem LICENSE (código do próprio autor) | (a) GPL-3.0-or-later (recomendado — permite reuso literal dos três); (b) licença permissiva + reimplementação total sem cópia | Sem decisão, **nenhuma linha** dos projetos GPL pode ser copiada |
| Q3 | Licenciar o PhaseZero atual | O repo do usuário não declara licença | Adicionar LICENSE ao PhaseZero para permitir reuso formal no Unified | Reuso do próprio código fica juridicamente implícito (aceitável se mesmo autor/titular, mas frágil se houver contribuições de terceiros) |
| Q4 | Escopo v1: só emulação+jogos, ou também boot/VM/Waydroid/homelab herdados do PhaseZero? | `linux/pz` cobre GRUB, Windows VM, Waydroid, homelab | Recomendação: **fora do v1** (NON-GOALS) | Escopo inflado ameaça as Fases 1–6 |
| Q5 | Distribuição primária: Flatpak (modelo RetroDECK) com helper host opcional? | ADR-0003 recomenda híbrido | Confirmar aceitação do custo: portais, permissões, helper privilegiado fora do sandbox | Define packaging, CI e supply chain inteiros |
| Q6 | Orçamento de hardware para a matriz de testes (Deck LCD/OLED, docks, TVs) | §13.4 exige matriz física | Definir dispositivos disponíveis reais | Sem isso, itens da matriz ficam "não verificados em hardware" |
| Q7 | Idioma primário da UI e dos textos de erro | Códigos de erro estáveis + títulos humanos | pt-BR primeiro (usuário) com chaves i18n desde o início (recomendado) | Retrabalho de i18n |
| Q8 | Telemetria/diagnóstico: pacote de suporte é sempre manual? | §14 exige visualização antes de exportar | Recomendação: 100% manual, zero telemetria automática | Confiança do usuário; requisitos de privacidade |
| Q9 | Suporte a multi-usuário (modelo RetroDECK multi_user.sh) no v1? | RetroDECK suporta múltiplos usuários | Recomendação: adiar para v2, mas modelar `device/profile` no schema desde já | Migração de schema depois |
| Q10 | Política de canais: nomes `stable/beta/dev` e cadência | §10.1/§15 | Definir cadência de release e política de sunset | Afeta UPDATE-AND-ROLLBACK e infraestrutura CI |
