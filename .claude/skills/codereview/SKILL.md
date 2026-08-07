---
name: codereview
description: Code review sênior das últimas mudanças do open-m711pro (working tree ou últimos commits), focado em correção do protocolo, manutenibilidade e segurança de hardware. Apenas reporta problemas com arquivo/linha e sugestão — não aplica correções. Use antes de commitar/abrir PR, ou quando pedirem "revisa o que mudou".
---

# Code Review Sênior — Últimas Mudanças

## Passo 0 — entenda a INTENÇÃO antes de julgar

Leia o plano (se houver) e o diff. Reveja o que **mudou** (`git diff`, working tree ou últimos commits), não o repo inteiro. Um achado pré-existente adjacente ao diff conta — a urgência é maior, não menor.

## Os três pilares

### 1. Correção do protocolo
- Todo byte enviado ao mouse tem **origem em captura real** documentada no `docs/PROTOCOL.md`? Chute mandado pro hardware é o bug nº 1 aqui.
- O **checksum** é calculado pela função central (não hardcoded) e fecha (`soma ≡ 0x55`)?
- Endereço, opcode, ordem RGB e tamanho batem com o PROTOCOL.md?
- Existe **teste de byte-match** contra uma captura conhecida pro código novo? Sem ele, não há prova.

### 2. Manutenibilidade
- **Stdlib puro** mantido? Dep nova tem justificativa?
- Nomes claros, funções pequenas, sem duplicar a lógica de checksum/builder.
- Constantes mágicas (endereços, IDs) nomeadas e comentadas com a referência do PROTOCOL.md.

### 3. Segurança de hardware & robustez
- **Device não encontrado / sem permissão** → mensagem útil, não traceback cru.
- Nenhum comando destrutivo/irreversível sem aviso e sem caminho de rollback conhecido.
- `ioctl`/`open` de `/dev/hidraw` com `try/finally` fechando o fd.
- Feature nova de hardware que ainda é 🚧 tentativa no PROTOCOL.md não deveria ir "ligada" por padrão.

## Também verifique

- **Código morto / fallback obsoleto** — builder de registrador que ninguém chama?
- **Duplicação viva** — se eu consertar o checksum aqui, todos os builders pegam?
- **Simplificação** — só com o código na mão; antes de encurtar, `git blame`: se a linha veio de um fix (ex.: tratamento de device ausente), o guard fica.
- **PROTOCOL.md em dia** — o código implementou algo que o doc não registra (ou vice-versa)?

## Antes de reportar — precisão > cobertura

Não invente problema. Cada achado precisa de arquivo:linha e do porquê concreto (que input/estado causa a falha). Se não reproduz, marque como "possível" e diga o que confirma.

## Severidade e formato

Classifique cada achado: **🔴 crítico** (byte sem captura / checksum errado / device sem tratamento), **🟡 médio** (manutenibilidade, duplicação), **⚪ baixo** (estilo). Formato: `arquivo:linha — [severidade] problema → sugestão`.

## Termine com um VEREDITO

Não só a lista: uma frase — "pode commitar", "corrigir os 🔴 antes", ou "falta teste de byte-match / captação de evidência". **Esta skill não aplica correções** — só reporta.
