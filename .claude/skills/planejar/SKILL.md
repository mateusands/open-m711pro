---
name: planejar
description: Planejamento de fix/feature ANTES de escrever código no open-m711pro — reformula o objetivo com critério de aceite, faz só as perguntas bloqueantes (cada uma com default), mapeia o raio de impacto por grep, decide a forma da mudança, roda os gates do projeto (byte com origem em captura · sem dep nova · protocolo documentado) e escreve o plano de teste, e então PARA. A execução depois do OK é a skill `coder`. Use ao receber "quero arrumar X / quero mapear a função Y".
---

# Planejar — antes da primeira linha de código

Esta skill decide **o quê** e **como**, e para antes de codar. A execução é a skill `coder`.

## Regra de ouro — esta skill NÃO escreve código

O produto do planejar é um **plano**, não um diff. Se você se pegou editando `m711led.py`, saiu do escopo.

## Proporcionalidade

A cerimônia escala com o risco:
- **Trivial** (renomear, docstring, ajustar CLI): um parágrafo e segue.
- **Toca hardware** (novo comando enviado ao mouse) ou **muda estrutura**: plano completo, todos os passos.

## Investigue antes de perguntar

Leia o `docs/PROTOCOL.md` e o código antes de perguntar qualquer coisa. Pergunta cuja resposta está no repo não se faz.

## Passos

**0. Problema REAL** — reformule o objetivo com suas palavras + critério de aceite verificável ("o LED muda pra azul rodando `m711led.py azul`").

**1. Onde isso vive** — qual arquivo/função, e qual registrador/endereço do PROTOCOL.md está envolvido.

**2. Raio de impacto (grep, não intuição)** — quem chama a função que vou mexer? Tem lógica gêmea (ex.: checksum usado em vários builders)? Mudou o formato do pacote → quantos comandos quebram?

**3. Forma da mudança** — a menor mudança que resolve. Feature nova de hardware **nasce atrás de captura confirmada**, não de suposição.

**4. Gates do projeto (rodar AGORA)** — pontos de parada:
   - **Origem do byte**: todo byte novo mandado ao mouse tem captura real por trás? Se não → skill `captura` primeiro.
   - **Protocolo documentado**: o registrador está no `docs/PROTOCOL.md` com confiança ✅? Se 🚧 → capturar mais amostras.
   - **Dependência nova**: o repo é **stdlib puro**. Adicionar lib (hidapi, PyQt…) precisa de justificativa explícita no plano.
   - **Segurança de hardware**: o comando pode deixar o mouse em estado ruim? Existe comando conhecido pra reverter?

**5. Plano de teste (vem ANTES do código) — SDD → BDD → TDD**
   - **SDD**: qual o contrato ("build_X(a,b) reproduz o pacote da captura Y").
   - **BDD**: cenários ("dado azul, quando build_led_color(0,0,255), então bytes == captura conhecida").
   - **TDD**: qual teste falha primeiro e em que arquivo (ex.: `tests/test_protocol.py`).

**6. Validação** — como se prova (byte-match contra captura **e** teste no hardware real), não "rodou sem erro".

**7. Risco · rollback** — o que pode dar errado no hardware, e como voltar (comando/valor anterior).

## Formato de saída — o plano

Apresente o plano no chat (features maiores: salve em `docs/plans/AAAA-MM-DD-<slug>.md`). Estrutura:

```
# Plano — <título>
## Objetivo (minhas palavras) + critério de aceite
## Perguntas bloqueantes (0–3, cada uma com default)
## Premissas (numeradas, falsificáveis)
## Estado atual (verificado no código/PROTOCOL.md)
## Raio de impacto
## O que muda — e o que NÃO muda
## Gates (origem do byte · protocolo · dep nova · hardware)
## Teste — SDD → BDD → TDD (qual falha primeiro, em que arquivo)
## Validação (byte-match + hardware)
## Risco · rollback
## Veredito
```

## Termine com um VEREDITO

Uma frase: "pronto pra `coder`" ou "bloqueado por <gate/captura faltando>". E **PARE** — não comece a implementar.
