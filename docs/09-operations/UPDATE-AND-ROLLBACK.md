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

## Compatibilidade externa (FM-10/§11.5)

Na subida e no doctor: comparar {SteamOS, Steam Client, Decky} com a Compat Matrix embarcada + atualizável por canal; incompatibilidade conhecida ⇒ capacidades afetadas entram em modo degradado explícito com aviso — nunca tentar mutação sob incompatibilidade conhecida.
