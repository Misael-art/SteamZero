# UPDATE-AND-ROLLBACK — atualização e reversão da própria plataforma

## Atualização (é uma transação como qualquer outra)

```
check (canal→versão alvo, changelog, requisitos)
→ plan (diff de versão, migrações de dados a executar, espaço)
→ backup (state.db + configs geridas + manifesto da versão atual)
→ stage (nova versão baixada e verificada: hash+assinatura)
→ apply (Flatpak: novo commit; nativo: pacote; AppImage: arquivo novo)
→ verify (daemon novo sobe em modo verificação, roda self-test + migrações em cópia)
→ activate (troca efetiva; migrações reais com journal)
→ test (doctor pós-update)
→ commit (versão anterior retida por política)
```

- Flatpak facilita: commits OSTree antigos ficam disponíveis (`flatpak update --commit=` para reversão exata) — razão de peso do ADR-0003.
- Update **nunca** roda automaticamente durante gameplay ou bateria baixa; agendável; sempre com consentimento (canal stable).

## Rollback de plataforma

- `steamzero platform rollback` → volta ao commit/pacote anterior + restaura state.db do backup da atualização **somente se** as migrações forem incompatíveis (senão mantém dados novos — regra RB-6: dados criados depois não são destruídos sem aviso; a UI explica a janela de perda).
- Testado por RT-14 (falha de migração no meio ⇒ restauração íntegra).

### Bootstrap nativo atual

Enquanto o M14 não entrega o canal assinado, o host BigLinux usa releases imutáveis
em `/opt/steamzero/releases` e o ponteiro atômico `/opt/steamzero/current`. O comando
`bigsudo /usr/local/sbin/steamzero-host rollback --release <id>` verifica manifesto, hashes,
permissões e smokes antes da troca. O procedimento reproduzível e seus limites estão
em [HOST-INSTALL.md](HOST-INSTALL.md).

O fluxo operacional recomendado é agora o controlador transacional, sem build
local e sem uma segunda implementação do instalador:

```bash
rtk .venv/bin/python tools/release_host.py update --to origin/main --plan
rtk .venv/bin/python tools/release_host.py update --to origin/main
```

Ele mantém lock global, journal write-ahead, escolhe automaticamente como
rollback a release ativa integralmente verificada e reverte se qualquer prova
pós-ativação falhar. Reexecução recupera a transação incompleta. O resultado
`deploymentHealthy=true` cobre release, daemon, CLI, doctor, units, Game Mode e
QML offscreen; certificação física continua separada e exige o operador. O
contrato completo está em
[RELEASE-HOST-AUTOMATION.md](RELEASE-HOST-AUTOMATION.md).

Novas instalações usam manifesto v2 e ID canônico `<versão>-<commit[0:12]>`; o
commit completo e o estado limpo da fonte são obrigatórios. Manifests v1 permanecem
aceitos apenas para verificar e reverter releases legadas já instaladas. Eles não
podem ser usados como evidência de proveniência de uma nova publicação; a auditoria
retrospectiva está em [RELEASE-LEDGER.md](RELEASE-LEDGER.md).

## Compatibilidade externa (FM-10/§11.5)

Na subida e no doctor: comparar {SteamOS, Steam Client, Decky} com a Compat Matrix embarcada + atualizável por canal; incompatibilidade conhecida ⇒ capacidades afetadas entram em modo degradado explícito com aviso — nunca tentar mutação sob incompatibilidade conhecida.
