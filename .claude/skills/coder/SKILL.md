---
name: coder
description: Execução de um plano aprovado no open-m711pro — a disciplina do ATO de escrever código Python, entre a skill `planejar` (antes) e a `codereview` (depois). Confirma que edita o arquivo certo, força TDD com prova do Red (byte-match contra captura), aplica as convenções do repo, nunca manda byte não-validado pro hardware, e para quando uma premissa cai. Use ao implementar um fix/feature já planejado.
---

# Coder — o ato de escrever o código

`planejar` decide **o quê**. `codereview` julga **o que ficou pronto**. Esta skill governa o **meio**.

## O que esta skill NÃO faz

- **Não planeja.** Sem plano aprovado, volte pra `planejar`.
- **Não substitui a `codereview`.** O auto-review do §5 é higiene, não revisão independente.
- **Não commita nem pusha sozinha.** Ver §7.

## 1. Pre-flight

| # | Checagem | Como |
|---|----------|------|
| 1 | **Edito o arquivo certo?** | O script/módulo que o usuário roda de verdade (`m711led.py`), não uma cópia |
| 2 | **Tem lógica gêmea?** | `grep` pelo conceito (`checksum`, `build_`, `find_hidraw`). Achou dois? o plano diz se muda os dois |
| 3 | **Branch em dia** | `git fetch` primeiro; nasce da branch de trabalho combinada |
| 4 | **Baseline verde anotado** | rode `pytest` **antes** e anote o número; sem baseline, "quebrei" e "já estava quebrado" se confundem |
| 5 | **Hardware acessível** | pra testar de verdade: dongle plugado, mouse ligado (2.4G), **fora da VM**, `/dev/hidraw` com acesso |

## 2. O ciclo, com prova (Red → Green → Refactor)

O **Red tem que ser mostrado**, não alegado.

1. **SDD** — escreva o cabeçalho do teste primeiro: qual o contrato, de qual **captura** ele deriva, e por quê.
2. **BDD** — `test_<função>_<cenário>`: "build_led_color(0,0,255) reproduz o pacote azul da captura".
3. **Red** — rode e **cole a saída da falha**. Um teste que passaria de qualquer jeito não prova nada.
4. **Green** — o **mínimo** pra passar.
5. **Refactor** — limpe sem quebrar o verde.

**A prova de ouro deste repo:** para qualquer código que monta pacote, o teste compara os bytes gerados **byte a byte com uma captura real conhecida** (como `08070000a00702ff000096ffbf0000004a` = vermelho). Se bate, o pacote está certo por construção.

## 3. Convenções enquanto escreve

- **Python stdlib puro.** Sem dep nova sem justificativa no plano.
- **Checksum sempre pela função central** — nunca hardcode o byte.
- **`hidraw` via `ioctl(HIDIOCSFEATURE)`**, interface 1, Report ID `0x08`.
- **Erro claro quando o device não é achado** (dongle? na VM? udev?), nunca um traceback cru.
- **Nunca refatore sem necessidade.** Simplificação que perde tratamento de erro é regressão.

### A armadilha nº 1 deste projeto

**Nunca mande pro hardware um byte que você não validou contra uma captura real.** Um pacote inventado (checksum errado, endereço chutado) pode deixar o mouse em estado estranho — e não gera erro no Python, o `ioctl` "sucede". Antes de qualquer `send_feature`, pergunte: esses bytes têm captura por trás? o teste de byte-match passa?

## 4. Regra de parada

**Se uma premissa do plano cair, pare e avise.** Gatilhos:
- os bytes capturados não são como o plano supôs (o registrador era outro, o checksum tem exceção);
- o "fix de uma linha" começou a exigir mudar o formato do pacote;
- pra avançar você precisaria **chutar** um byte sem captura → volte pra skill `captura`.

## 5. Auto-review do próprio diff

- [ ] Todo byte enviado tem **captura de origem** e passa no byte-match?
- [ ] **Duplicação**: mexi no checksum/builder e conferi todos os usos?
- [ ] **Erro de device** tratado com mensagem útil?
- [ ] **Fronteira**: o diff mudou só o que o plano disse?
- [ ] **Teste**: baseline antes × depois, e o teste novo **falha** sem o fix?
- [ ] **PROTOCOL.md** atualizado se um registrador novo foi implementado?

⚠️ **Teste verde ≠ funcionou no mouse.** O byte-match prova que o pacote está certo; só o **teste no hardware real** prova que o mouse obedeceu. Se não testou no mouse, **diga que não testou**.

## 6. Commits e entrega

- **Um commit por unidade revertível**, com o teste junto.
- Mensagem no padrão `feat(led): ...` / `fix(protocol): ...` — diga o **efeito**.
- **PROIBIDO `git commit`/`git push` sem ordem explícita.** Ordem pra commitar não é ordem pra pushar.
- Nunca `--no-verify`, nunca commitar `.pcapng` (estão no `.gitignore`).

## 7. Relato final — honesto

1. **O que mudou** (uma frase por commit).
2. **A prova**: baseline × depois do `pytest`, e o byte-match que passou.
3. **O que foi validado e onde** — e explicitamente **o que NÃO foi testado no hardware**.
4. **Risco + rollback** (como voltar o valor anterior no mouse).
5. **O que ficou de fora de propósito**, com o motivo.
