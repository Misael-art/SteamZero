# Componente: telemetria local sanitizada

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base do incremento: `e75b091`

## Hipótese a reproduzir

O job informa progresso e erro, mas não preserva fatos diagnósticos sobre DNS,
proxy, ambiente e executor. Além disso, o token já validado ainda é copiado para
`job.params_json`, ampliando desnecessariamente a custódia da autorização.

A reprodução deve exigir diagnósticos locais úteis sem URL completa, endereço
IP, valor de proxy, variável arbitrária ou token. O worker deve continuar
recuperável usando somente `planId` e a autorização já persistida no plano
protegido, mantendo compatibilidade com jobs legados.
