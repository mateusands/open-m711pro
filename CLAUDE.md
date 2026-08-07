# CLAUDE.md — convenções do open-m711pro

Guia de contribuição e disciplina de desenvolvimento do projeto. O **quê** o
projeto é está no [README.md](README.md); **como** o protocolo funciona está em
[docs/PROTOCOL.md](docs/PROTOCOL.md); **como se trabalha** está aqui.

## Regras de ouro

1. **A fonte da verdade é `docs/PROTOCOL.md`.** Todo byte enviado ao mouse deriva
   de uma descoberta documentada lá, com evidência de captura.
2. **Nunca mande pro hardware um byte que você não validou contra uma captura
   real.** Um pacote inventado pode deixar o mouse em estado estranho — e o
   `ioctl` "sucede" sem erro. Antes de qualquer envio: o byte-match passa?
3. **Python puro (stdlib).** Sem dependências externas sem justificativa explícita.
4. **Nunca `git commit`/`git push` sem ordem explícita do dono.** Ordem para
   commitar não é ordem para pushar; PR é passo separado.

## Estrutura do projeto

```
main.py               # ponto de entrada fino (GUI sem args, CLI com args)
m711pro/
├── core/
│   ├── protocol.py   # construção de pacotes + checksums — LÓGICA PURA, sem I/O
│   └── device.py     # comunicação hidraw (find_devices, send_color, send_off)
├── colors.py         # cores nomeadas (CLI) + paleta (GUI)
├── cli.py            # interface de linha de comando
└── gui.py            # interface gráfica (tkinter)
tests/                # byte-match contra capturas (pytest)
docs/PROTOCOL.md      # a fonte da verdade do protocolo
```

Regras de camada:
- **`core/protocol.py` é lógica pura** (nada de I/O) — é o que os testes de
  byte-match exercitam. Todo builder de pacote mora aqui.
- **`core/device.py` isola o I/O** (hidraw/ioctl). Só ele fala com o hardware.
- **`cli.py` e `gui.py` não constroem pacote nem falam hidraw direto** — chamam
  `device.send_color()` / `device.send_off()`.

## Fluxo de trabalho (Git)

- **Trabalhe sempre em branch; nunca commite direto na `main`.**
- Ciclo: `branch → PR → dono revisa/faz merge → sincroniza main → apaga a branch`.

### Nome de branch

Padrão: `tipo/descricao-curta`

```
feat/led-brilho
fix/checksum-interno
refactor/find-device
capture/dpi
docs/protocolo-botoes
```

### Mensagem de commit — Conventional Commits

Formato: `tipo(escopo): descrição no imperativo`

| Tipo | Uso |
|------|-----|
| `feat` | função nova (comando, registrador mapeado) |
| `fix` | correção de bug |
| `refactor` | reestrutura sem mudar comportamento |
| `test` | testes |
| `docs` | README, PROTOCOL.md, docs/ |
| `chore` | infra do repo |
| `ci` | automação |

**Escopos comuns:** `led`, `protocol`, `cli`, `capture`, `device`, `repo`, `docs`.

Exemplos:
```
feat(led): adiciona comando de desligar (modo 0x04)
fix(device): acha o mouse em qualquer modo (FA07/FA08)
docs(protocol): documenta o checksum interno do registrador 0xA0
test(led): byte-match do off contra a captura
```

### Pull Request

- **Título** segue a convenção de commit.
- **Descrição** com: *o que mudou*, *como testar* (comando + prova), e *evidência*
  (byte-match e/ou o resultado no hardware real).
- **PRs pequenos e focados — uma responsabilidade por PR.** Prefira vários PRs
  pequenos a um gigante.

## Qualidade e testes

- **Python stdlib puro**; acesso ao hardware via `hidraw` + `ioctl`.
- **TDD obrigatório para a lógica de protocolo:** `SDD (spec) → BDD (Given/When/Then)
  → teste vermelho antes do código`. Sem exceções.
- **Todo builder de pacote tem teste de byte-match** contra uma captura real
  conhecida — é a prova de que o pacote está certo por construção.
- **Checksums pela função central**, nunca hardcoded.
- Testes em `tests/` (pytest). Capturas `.pcapng` **não** entram no repo (`.gitignore`).

## Idioma

- **Código** (nomes de variáveis, funções, tipos) e **mensagens de commit** em
  **inglês**. Simplicidade e alcance internacional.
- **Documentação e comentários** podem ser em português.

## Segurança de hardware

- Comando que muda estado do mouse precisa de um caminho de reversão conhecido
  (ex.: `off` reverte o LED). Documente no PROTOCOL.md.
- Função nova ainda `🚧 tentativa` (1 amostra só) não vai "ligada" por padrão.

## Assistência por IA (Claude Code)

As skills em [`.claude/skills/`](.claude/skills/) codificam este fluxo:

```
iniciar-sessao → planejar → coder → codereview → finalizar-sessao
                     ▲
        captura → protocolo   (loop de engenharia reversa)
```

Comece a sessão pela skill `iniciar-sessao` (carrega os docs) e encerre pela
`finalizar-sessao` (consolida as descobertas).

## Licença

GPL v3 (a confirmar).
