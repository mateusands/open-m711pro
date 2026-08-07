# Roteiro de mapeamento — DPI

A captura em lote anterior mostrou `0x00` e `0x0c` mudando, mas os valores não
fecharam. Com a leitura (`read_register`) funcionando, deu pra **varrer a memória
inteira do mouse** e o impasse se resolveu quase todo antes de qualquer pcap.

## Ferramenta

`tools/dump_config.py` — varre `0x00..0xF8` e imprime o que o mouse responde.
É **somente leitura**: só usa o opcode `0x08` (requisição de leitura, já
validado); nunca `0x07` (escrever) nem `0x04` (commit). Não altera estado.

```bash
python3 tools/dump_config.py                 # varredura completa
python3 tools/dump_config.py --addr 0C       # um endereço só
python3 tools/dump_config.py > /tmp/dpi-800.txt
```

## Dump de referência (hardware real, 2026-08-07)

```
00: 01 54 05 50 00 55 00 55     20: bd bd 00 db bd bd 00 db
08: 00 55 00 55 07 07 00 47     28: bd bd 00 db ff 00 00 56
10: 17 17 00 27 2f 2f 00 f7     30: 00 00 ff 56 00 ff 00 56
18: 5f 5f 00 97 bd bd 00 db     38: ff ff 00 57 ff 80 00 d6
40: ff 00 ff 57 ff 7d 7d 5c     60: 01 01 00 53 01 02 00 52
48: 7d 7d ff 5c 01 54 01 54     68: 01 04 00 50 01 08 00 4c
50: 03 52 00 55 ff 00 ff 57     70: 01 10 00 44 00 00 00 55
58: 03 52 80 d5 03 52 00 55     78: 09 00 00 4c 00 00 00 55
80: 00 00 00 55 05 00 00 50     90..9F: 00 00 00 55 (zerado)
88: 05 00 00 50 05 00 00 50     A0: 04 00 00 00 96 ff bc
                                 A8: 55 | 01 54 | AC..FF: ff (não usado)
```

### Descoberta transversal: o checksum ≡ `0x55` vale **por registro** ✅

Cada registro da memória fecha em `0x55 (mod 256)` — a mesma regra do pacote
externo e do bloco interno do LED, agora confirmada como **regra geral do chip**.
O tamanho do registro varia (é o campo `LEN` do pacote de escrita):

| Região | Tamanho do registro | Verificação |
|--------|--------------------|-------------|
| `0x00`–`0x0B` | 2 bytes (`valor` + cksum) | `01+54 = 0x55` ✅ |
| `0x0C`–`0x4B` | 4 bytes (3 dados + cksum) | `2f+2f+00+f7 ≡ 0x55` ✅ |
| `0x60`–`0x73` | 4 bytes | `01+10+00+44 = 0x55` ✅ |
| `0xA0` | 7 bytes (LED, já conhecido) | ✅ |

Todos os 20+ registros do dump conferem. Isso é o que valida que o dump foi lido
certo — e dá o `LEN` a usar na escrita de cada região.

## O endereço é de 16 bits ✅

A captura mostrou o app usando **dois** bytes de endereço, e varrendo muito além
do que a leitura atual alcança:

```
08 08 00 01 00 0a     ← página 0x0100
08 08 00 02 e0 0a     ← página 0x0200
08 08 00 19 81 0a     ← até 0x1981
```

E escrevendo em `0x0220`, `0x0240`, `0x0260`. O `build_read()` atual monta
`08 08 00 00 <addr> <len>` — só o byte baixo — então `tools/dump_config.py` cobre
apenas `0x0000`–`0x00FF`. **A região `0x0100`–`0x1981` (provavelmente
botões/macros) ainda não foi lida.** Estender o endereço para 16 bits é
pré-requisito pra mapear macros.

Também apareceu um provável **handshake** antes das escritas:
`08 01 00 00 00 04 62 30 61 58` — os 4 bytes de dados são ASCII `b0aX`. As
escritas de LED funcionam sem ele, então não parece obrigatório. 🚧

## Mapa de memória

| Endereço | Conteúdo | Confiança |
|----------|----------|-----------|
| `0x00` | `01` — estágio de DPI ativo (escrito com `LEN 02`) | ✅ estrutura |
| `0x02` | `05` — **quantidade de estágios** (o app escreve exatamente 5) | ✅ |
| `0x0C`–`0x1F` | **tabela de DPI: 5 estágios × 4 bytes** (`X X 00 ck`) | ✅ |
| `0x20`–`0x2B` | resto da tabela, **não escrito** pelo app (lixo em `bd`) | ✅ |
| `0x2C`–`0x3F` | **cor de cada estágio: 5 × 4 bytes** (`R G B ck`) | ✅ |
| `0x4C` | **DPI Effect**: `01` = Steady, `00` = desligado | ✅ isolado em diff |
| `0x4E`, `0x50` | `01`, `03` — resto do grupo do DPI Effect | 🚧 hipótese |
| `0x60`–`0x77` | **mapa de botões: 5 × 4 bytes** (`01 <bitmask> 00 ck`) | ✅ estrutura |
| `0x78` | `09` — "Mouse sensitivity" (app mostra 10, base zero)? | 🚧 hipótese |
| `0xA0` | LED (já mapeado e implementado) | ✅ |
| `0x0220`/`0x0240`/`0x0260` | escritos com `02 82 ?? 00 42 ?? 00 ck` | 🚧 desconhecido |

### A tabela de DPI (`0x0C`) — 5 estágios

O app escreve exatamente 5 entradas, em três pacotes: `0x0C` (`LEN 08`, estágios
1–2), `0x14` (`LEN 08`, estágios 3–4) e `0x1C` (`LEN 04`, estágio 5). Bate com
`0x02 = 05`.

```
0x0C: 07 07 00 47     estágio 1 —    700 DPI
0x10: 17 17 00 27     estágio 2 —   2000 DPI
0x14: 2f 2f 00 f7     estágio 3 —   4000 DPI
0x18: 5f 5f 00 97     estágio 4 —   8000 DPI
0x1C: bd bd 00 db     estágio 5 —  16000 DPI
0x20..0x28: bd bd 00 db   ← não escrito pelo app; ignorar
```

Os **dois primeiros bytes são iguais** em todas as entradas → são **X e Y**, hoje
travados juntos. Isso confirma que o DPI tem eixos independentes no formato.

A região é confirmada por vizinhança: `0x2C` em diante são as **cores dos
estágios** (também 5, no mesmo padrão de `LEN` 8/8/4) — é como o mouse indica o
nível de DPI pelo LED. O estágio 2 (`00 00 ff`, azul) e o 3 (`00 ff 00`, verde)
batem exatamente com os quadradinhos do app, o que trava a ordem da tabela.

### A codificação — o passo é ~83,33 DPI ✅

Os valores que o app mostra (screenshot da tela "Advanced") cruzados com a
memória e com os dois valores escritos durante a captura dão 6 pares:

| byte | n+1 | DPI no app | origem |
|------|-----|------------|--------|
| `07` | 8 | 700 | estágio 1 |
| `0b` | 12 | 1000 | escrito na captura |
| `17` | 24 | 2000 | estágio 2 |
| `2f` | 48 | 4000 | estágio 3 |
| `5f` | 96 | 8000 | estágio 4 |
| `bd` | 190 | 16000 | estágio 5 |

`(n+1)/DPI = 0,0120` em quatro dos seis → **`DPI = (n+1) × 250/3 ≈ (n+1) × 83,33`**.

| Hipótese | Acertos | Veredito |
|----------|---------|----------|
| `n = round(DPI × 0,012) − 1` | 5/6 (erra o 16000: prevê `bf`) | 🚧 finalista |
| `n = round(DPI ÷ 84,21) − 1` (escala ancorada em 190↔16000) | 5/6 (erra o 8000: prevê `5e`) | 🚧 finalista |
| `DPI = (n+1) × 100` | 0/6 | ✗ **falsificada** |
| `DPI = (n+1) × 50` | 0/6 | ✗ **falsificada** |
| DPI cru 16 bits | — | ✗ (só há 2 bytes, e eles são X e Y iguais) |

---

# Experimentos decisivos

Ciclo para cada um: mude **uma** coisa no app (na VM) → **Aplicar** → **feche o
app** → devolva o dongle da VM pro host → rode o dump no Linux → `diff`.

```bash
python3 tools/dump_config.py > /tmp/e1.txt
diff -u /tmp/dpi-baseline.txt /tmp/e1.txt
```

> Se o dump vier todo `<sem resposta>`, o dongle ainda está capturado pela VM.

### E1 — desempatar as duas finalistas
No app: **estágio 1 = 10000 DPI**. Depois:
`python3 tools/dump_config.py --addr 0C --len 4`

| `0x0C` volta | Codificação |
|--------------|-------------|
| `77 77 00 d7` | `n = round(DPI × 0,012) − 1` ✅ |
| `76 76 00 d9` | `n = round(DPI ÷ 84,21) − 1` ✅ |
| outra coisa | me mande — a tabela acima está errada |

12000 DPI separa por 2 (`8f` vs `8d`), se quiser margem maior. 5000, 6000 e
15000 também divergem; 3000 **não** serve (as duas dão `23`).

### E2 — linearidade
No app: **estágio 1 = 1600 DPI**. Espera-se `0f` (×100) ou `1f` (×50).
Confirma que a relação é linear e não uma tabela de índices arbitrária.

### E3 — o índice do estágio ativo
No app: selecione o **estágio 3** (só selecionar, **não** edite o número).
Espera-se que só `0x00` mude (`01` → `03`, ou `02` se for base zero).

### E4 — a quantidade de estágios
No app: reduza para **3 estágios**. Espera-se `0x02`: `05` → `03`, e as entradas
`0x14`+ virando padding.

### E5 — X/Y independentes
No app: ligue **eixos independentes**, X = 800, Y = 1600.
Espera-se `0x0C` = `07 0f 00 ...` (×100) — provando que byte 0 = X e byte 1 = Y.
Se o app não tiver essa opção, pule e me avise.

### E6 — a cor do estágio
No app: cor do **estágio 1** = verde puro.
Espera-se `0x2C`: `ff 00 00 56` → `00 ff 00 56`. Fecha o significado da região
`0x2C` e desacopla cor de DPI no diff.

### E7 — polling (de brinde)
No app: **1000 Hz**, depois **500**, **250**, **125**. Dump entre cada.
`0x78` hoje é `09`. Se for divisor → `01 02 04 08`; se for Hz/10 → `64 32 19 0d`.
Qualquer uma das duas já resolve o polling junto.

---

# Trilha B — a captura USB (a evidência de escrita)

Os experimentos acima decodificam a memória, mas eles mostram só o **resultado**;
o `docs/PROTOCOL.md` exige a evidência do **pacote que o app manda**. Então, uma
captura curta ainda é necessária antes de implementar a escrita — é ela que prova
o `LEN` e o endereçamento do pacote `0x07` para a região de DPI.

## Preparação

- Mouse no **modo 2.4G (dongle)**, app aberto **na VM** e detectando.
- `sudo modprobe usbmon` · `lsusb | grep 25a7` (anote bus/addr).
- **Não mexa o mouse** durante a captura (o movimento gera milhares de
  interrupt-IN). Clique no app pelo touchpad/teclado.

```bash
sudo dumpcap -i usbmon0 -a duration:120 -w /tmp/dpi.pcapng
sudo chown "$USER": /tmp/dpi.pcapng
```

## Ações (ordem exata, pausa de ~3 s entre cada, "Aplicar" após cada)

1. **Aplicar sem mudar nada** — linha de base; o que mudar aqui é ruído do app.
2. Estágio 1 = **800**
3. Estágio 1 = **1600**
4. Estágio 1 = **3200**
5. Estágio 2 = **400**
6. Selecionar **estágio 3** (sem editar valor)
7. Reduzir para **3 estágios**
8. Polling **1000 Hz**
9. Polling **125 Hz**

Me mande `/tmp/dpi.pcapng` e diga quais ações você pulou. Eu faço o diff de
blocos, cruzo com o mapa de memória acima e sigo pra `protocolo` (documenta) e
`coder` (implementa com teste de byte-match).

## Armadilhas

- O app reescreve a config **inteira**: o commit (`0x04`) e o LED (`0xA0`)
  aparecem em todos os blocos. O sinal está em `0x00`, `0x02` e `0x0C`+.
- Os *responses* de leitura não aparecem nos campos do tshark — precisa parsear
  o `-x` no offset `0x40` (ver `docs/PROTOCOL.md`).
- Pra testar o código no Linux, o mouse precisa **sair** da VM.
