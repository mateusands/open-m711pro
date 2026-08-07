---
name: finalizar-sessao
description: Encerra a sessão de trabalho no open-m711pro — consolida as descobertas da sessão nos docs do repo (docs/PROTOCOL.md + README.md) e gera um resumo técnico do que foi feito e do que ficou pendente. Não commita/pusha sem ordem. Use ao final de cada sessão.
---

# Encerramento de Sessão

Agora o objetivo **não é codar**, é consolidar o que a sessão descobriu na **fonte da verdade do repo**.

## 1. Atualizar a documentação

- **docs/PROTOCOL.md** — se a sessão decodificou/confirmou algo (registrador novo, byte, checksum, exceção), registre no formato padrão (ver skill `protocolo`): endereço, layout, tabela valor→bytes com as capturas, confiança (✅/🚧) e a seção **Status / TODO** atualizada.
- **README.md** — se mudou o estado das funções (a tabela de status) ou o roadmap, atualize.
- Só documente o que tem **evidência de captura**. Hipótese sem 2+ amostras entra como 🚧 tentativa, dizendo o que falta capturar.

## 2. Gerar o resumo da sessão

Um resumo técnico (no chat; se quiser histórico versionado, `docs/sessions/AAAA-MM-DD.md`) com:
- **O que foi decodificado/implementado** — funções, registradores, código novo.
- **Provas** — quais capturas, quais testes de byte-match passaram, o que foi testado no **hardware real** (e o que **não** foi).
- **Pendências** — o que ficou pra próxima (itens do TODO), e qual a próxima captura óbvia.
- **Estado do mouse** — se a sessão deixou o mouse com alguma config alterada, registre.

## 3. Git

> ⚠️ **Nunca** `git commit`/`git push` sem ordem explícita. Nunca versionar `.pcapng` (estão no `.gitignore`). Nunca gravar dados sensíveis nos docs.

## O que responder ao usuário

1. Liste, curto, quais docs foram atualizados (ou "nenhuma atualização necessária").
2. Resumo de 3–5 linhas do que a sessão entregou + a próxima pendência.
3. Finalize com: "Sessão encerrada. Até a próxima!"
