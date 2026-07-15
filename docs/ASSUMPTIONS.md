# ASSUMPTIONS — premissas explícitas desta fundação

Cada premissa indica o que a invalidaria. Premissas invalidadas exigem revisão dos documentos que as citam.

| # | Premissa | Base | O que a invalida |
|---|---|---|---|
| A1 | Os clones em `Port_Steam/reference/` representam fielmente o estado atual dos projetos upstream | Commits registrados no WORKLOG (jul/2026, exceto RetroDECK mai/2026) | Releases upstream posteriores com mudanças estruturais |
| A2 | PhaseZero `linux/` é a direção estratégica do PhaseZero (o lado PowerShell é legado Windows) | `CLAUDE.md` descreve o monólito PS 5.1; `linux/pz` é a superfície nova e ativa (commit HEAD toca `linux/ai`) | Decisão do autor de continuar Windows-first |
| A3 | O titular do PhaseZero é o mesmo responsável por este projeto (reuso de código próprio é permitido) | Remote `Misael-art/PhaseZero`; e-mail do usuário | Contribuições de terceiros no histórico do PhaseZero |
| A4 | O produto-alvo roda em SteamOS 3.x (Arch imutável) e em desktops Arch/Fedora/Bazzite/Ubuntu | §4 e §13.5 do prompt mestre | Mudança da Valve para outra base (ex.: SteamOS futuro não-Arch) |
| A5 | Flatpak está disponível ou instalável em todos os alvos suportados | SteamOS inclui Flatpak; LinuxToys usa `pkg_flat` em ostree/deb/suse | Distros-alvo sem Flatpak viável |
| A6 | O usuário final possui legalmente seus dumps (política local-owned-dump-only é aceitável ao público-alvo) | §5.2 | — (política inegociável, não premissa de mercado) |
| A7 | Decky Loader continua existindo, porém instável entre atualizações do Steam Client | PhaseZero `linux/steamdeck/install-plugins.sh` e `decky-ws-client.py` já tratam Decky como opcional | Decky ser descontinuado (produto já não depende dele) ou estabilizado oficialmente pela Valve |
| A8 | SQLite está disponível em todos os alvos (bundled no runtime Python) | Python 3.11+ embute sqlite3 | Ambiente sem Python runtime empacotável (mitigado por Flatpak) |
| A9 | Nada nesta fundação foi validado em hardware Steam Deck; toda afirmação sobre Deck vem de análise estática dos quatro projetos e documentação pública | Ambiente de análise é um desktop Manjaro | — (limitação declarada, ver KNOWN-GAPS G5) |
| A10 | A árvore parcial de RetroDECK/components (manifest+recipe+prepare/update de amostras) é representativa do padrão de todos os componentes | 6.799 paths listados; estrutura por componente é homogênea (mesmos 5-6 arquivos por diretório) | Componentes com estrutura divergente em `archive_later/` |
