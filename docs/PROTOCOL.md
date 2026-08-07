# Protocolo do Redragon M711 Pro (chip Compx)

Documentação da engenharia reversa do mouse **Redragon M711 Pro** (wireless,
receptor 2.4G), obtida capturando o tráfego USB do software oficial (Windows,
rodando em VM) com `usbmon` + Wireshark.

## Identificação dos dispositivos

| Papel | VID:PID | Descrição USB |
|-------|---------|---------------|
| Receptor (dongle 2.4G) | `25A7:FA07` | `2.4G Wireless Receiver` |
| Mouse (via rádio/cabo) | `25A7:FA08` | `2.4G Dual Mode Mouse` |

> `25A7` = **Compx** (OEM comum de mouses wireless gamer).

Os comandos de configuração são enviados **para o receptor** (`FA07`), que
repassa pro mouse pelo rádio 2.4G. A configuração **não** funciona no modo cabo
nem por Bluetooth — apenas via dongle.

## Camada de transporte

Os comandos são **HID Feature Reports** (não interrupt/bulk):

| Campo | Valor |
|-------|-------|
| `bmRequestType` | `0x21` (Host→Device, Class, Interface) |
| `bRequest` | `0x09` (SET_REPORT) |
| `wValue` | `0x0308` (tipo 3 = Feature, Report ID `0x08`) |
| `wIndex` | `1` (interface 1) |
| `wLength` | `17` |

No Linux, envie via `ioctl(HIDIOCSFEATURE)` no `/dev/hidraw` correspondente à
**interface 1** do receptor.

## Formato do pacote (17 bytes)

```
08 07 00 <ADDR_HI> <ADDR_LO> <LEN> <DADOS...> <padding> <CHECKSUM>
│  │  │  └────────┬────────┘  │    └── até LEN bytes de dados
│  │  │           │           └── quantidade de bytes de dados (0x08, 0x04, 0x02...)
│  │  │           └── endereço de 16 bits na memória de config do mouse
│  │  └── sempre 00 (byte alto do endereço?)
│  └── opcode: 0x07 = escrever ; 0x04 = aplicar/commit ; 0x08 = ler
└── Report ID (0x08)
```

> O endereço ocupa os bytes **3 e 4**, e o `LEN` é o byte **5**. No LED
> (`08 07 00 00 A0 07`) isso lê como `ADDR=0x00A0`, `LEN=0x07`.

O app escreve **toda** a configuração como uma sequência de pacotes `0x07`
(um por região de memória) e finaliza com um pacote de commit (`0x04`).

## Checksum

A **soma de todos os 17 bytes** do pacote é sempre congruente a **`0x55` (mod 256)**.

```python
checksum = (0x55 - sum(primeiros_16_bytes)) & 0xFF
```

Verificado em vários pacotes distintos. (Descoberto notando que quando o byte de
modo mudava `0x02→0x04` (+2), um byte vizinho mudava `0xBF→0xBD` (−2), mantendo o
checksum final igual.)

## Registrador do LED — endereço `0x00A0`

```
08 07 00 00 A0 07 | 02 | RR GG BB | 96 FF BF | 00 00 00 | <cksum>
                    │    └─R─G─B┘
                    └── modo: 0x02 = ligado (estático) ; 0x04 = desligado
```

Confirmado com capturas de cores conhecidas:

| Cor definida no app | Bytes RGB em `0x00A0` |
|---------------------|-----------------------|
| Vermelho (255,0,0)  | `FF 00 00` |
| Verde (0,255,0)     | `00 FF 00` |

- Ordem dos bytes: **R, G, B**.
- `96 FF` ficaram constantes entre as capturas — provavelmente brilho/efeito
  (a mapear).

### Checksum interno do `0x00A0`

O 7º byte de dados (`BF` ligado / `BD` desligado) **não é fixo** — é um
**checksum interno** dos 7 bytes de dados, com a **mesma regra do externo**: a
soma dos dados fecha em **`0x55` (mod 256)**.

```python
inner = (0x55 - (mode + R + G + B + 0x96 + 0xFF)) & 0xFF
```

Isso explica tudo:
- vermelho/verde (modo `02`) → `inner = 0xBF`
- desligado (modo `04`) → `inner = 0xBD`

E foi **corroborado** pela captura de OFF (o `BD` cai naturalmente da fórmula com
`mode=04`), confirmando de uma vez o **liga/desliga** e o **checksum interno**.

### Liga / desliga

O byte de **modo** governa: `0x02` = ligado (cor estática), `0x04` = desligado.
A cor pode ser mantida ou zerada quando desligado — o modo é o que apaga.

### Layout completo do `0x00A0` (mapeamento em lote)

Os 6 bytes de dados foram totalmente decodificados:

```
08 07 00 00 A0 07 | EFEITO | R G B | VELOCIDADE | BRILHO | inner | 00 00 00 | cksum
```

| Byte | Campo | Valores observados |
|------|-------|--------------------|
| 0 | **EFEITO** | `00`=Ciclo · `01`=Respiração · `02`=Fixo · `04`=Off (todos confirmados por captura) |
| 1–3 | **R G B** | cor |
| 4 | **VELOCIDADE** | `96` padrão; `13` num efeito (menor = mais rápido) |
| 5 | **BRILHO** | `FF`=100%; abaixo é a % direta (50% = `0x32`). ✅ implementado |
| 6 | inner | checksum interno |

### Leitura do estado (nível 2) — DECODIFICADA ✅

O app lê a memória em pedaços via **requisição** `08 08 <addr> <len>` (Report ID
08, SET_REPORT). A **resposta** volta por **interrupt IN** como **Report ID 09**,
no mesmo layout:

```
09 08 <addr> <len> <dados...> <cksum>
```

> Atenção: os *responses* NÃO aparecem nos campos normais do tshark (bug do
> dissector usbmon) — foi preciso parsear o `-x` no offset `0x40`.

Exemplo real — ler o LED (`addr 0xA0`) devolveu `04 00 00 00 96 ff bc` =
`EFEITO · R · G · B · VELOCIDADE · BRILHO · inner` (idêntico à escrita).

Implementado em `device.read_led_state()`: envia a requisição por
`HIDIOCSFEATURE` e lê o report 09 do hidraw (`os.read` + `select`).

## Endereçamento de 16 bits ✅

O endereço do pacote tem **dois** bytes, não um. O LED (`0x00A0`) mascarava isso
por estar na página zero. A captura do app mostra a varredura completa:

```
08 08 00 00 00 0a     ← página 0x0000
08 08 00 01 00 0a     ← página 0x0100
08 08 00 02 e0 0a     ← página 0x0200
08 08 00 19 81 0a     ← até 0x1981
```

```
08 <op> 00 <ADDR_HI> <ADDR_LO> <LEN> <dados...> <cksum>
         └────────┬────────┘
                  └── endereço de 16 bits
```

A configuração principal vive em `0x0000`–`0x00A8`. As páginas `0x0100`+
(provavelmente botões/macros) ainda **não** foram lidas — a leitura atual só
monta o byte baixo.

### Checksum por registro ✅

A regra "soma ≡ `0x55` (mod 256)" não vale só para o pacote de 17 bytes e para o
bloco de dados do LED — vale para **cada registro da memória**, com o tamanho
dado pelo campo `LEN`:

| Região | `LEN` | Exemplo |
|--------|-------|---------|
| `0x0000`–`0x000B` | `02` | `01 + 54 = 0x55` |
| `0x000C`–`0x004B` | `04` (por entrada) | `2f + 2f + 00 + f7 ≡ 0x55` |
| `0x0060`–`0x0077` | `04` (por entrada) | `01 + 10 + 00 + 44 = 0x55` |
| `0x00A0` | `07` | LED |

Verificado contra todos os 20+ registros de um dump completo do hardware.

## Registrador de DPI — endereço `0x000C` ✅

```
08 07 00 00 0C 08 | X1 Y1 00 ck1 | X2 Y2 00 ck2 | 00 00 | <cksum>
                    └── estágio 1 ┘└── estágio 2 ┘
```

Cada estágio ocupa **4 bytes**: `X`, `Y`, `00`, checksum interno do registro.
`X` e `Y` são os eixos — o app os mantém iguais (eixos travados), mas o formato
suporta valores independentes.

São **5 estágios**, escritos em três pacotes:

| Endereço | `LEN` | Estágios |
|----------|-------|----------|
| `0x000C` | `08` | 1 e 2 |
| `0x0014` | `08` | 3 e 4 |
| `0x001C` | `04` | 5 |

`0x0020`–`0x002B` contém lixo (`bd bd 00 db`) e **não** é escrito pelo app.

### Codificação do valor ✅

```python
n = round(dpi * 0.012) - 1        # DPI -> byte
dpi = (n + 1) * 250 / 3           # byte -> DPI  (passo de ~83,33 DPI)
```

Confirmado com **6 valores conhecidos** lidos na tela do app oficial e cruzados
com a captura:

| DPI no app | Byte | Origem |
|------------|------|--------|
| 700 | `07` | estágio 1 (padrão do dono) |
| 1000 | `0b` | escrito durante a captura |
| 2000 | `17` | estágio 2 |
| 4000 | `2f` | estágio 3 |
| 8000 | `5f` | estágio 4 |
| **10000** | **`77`** | escrito durante a captura — o valor que desempatou |

> O 10000 foi o experimento decisivo: a hipótese concorrente (escala ancorada no
> máximo, passo 84,21) previa `76`. A captura trouxe `77`.

Pacotes de captura (todos fecham em `0x55`):

```
08 07 00 00 0c 08 07 07 00 47 17 17 00 27 00 00 88     estágio 1 =   700
08 07 00 00 0c 08 0b 0b 00 3f 17 17 00 27 00 00 88     estágio 1 =  1000
08 07 00 00 0c 08 17 17 00 27 17 17 00 27 00 00 88     estágio 1 =  2000
08 07 00 00 0c 08 77 77 00 67 17 17 00 27 00 00 88     estágio 1 = 10000
08 07 00 00 14 08 2f 2f 00 f7 5f 5f 00 97 00 00 80     estágios 3/4
08 07 00 00 1c 04 bd bd 00 db 00 00 00 00 00 00 d1     estágio 5
```

**Anomalia conhecida** 🚧: o estágio 5 lê `bd` (= 15833 DPI pela fórmula), mas o
app rotula "16000" (que daria `bf`). Como o estágio 5 nunca foi alterado nas
capturas, `bd` é provavelmente valor de fábrica no teto do firmware, com o app
arredondando o rótulo do slider. Falta capturar uma escrita explícita de 16000.

### Faixa aceita pela implementação

O código limita o DPI a **100–16000** e o byte resultante a **`0x00`–`0xBD`** —
o intervalo que já vimos o firmware segurar. Acima de `0xBD` é território nunca
observado, e a regra de ouro do repo proíbe mandar byte sem captura.

Consequência a respeitar em qualquer código que escreva a tabela: a conversão
**byte → DPI → byte é identidade apenas em `0x00`–`0xBD`**; de `0xBE` a `0xFF`
tudo colapsa em `0xBD`. Por isso, ao mudar um estágio, os outros quatro têm que
ser reescritos a partir dos **bytes lidos**, nunca reconstruídos a partir do DPI
— senão um estágio acima de `0xBD` seria rebaixado em silêncio.
(`device.read_dpi_bytes()` / `protocol.build_dpi_table_bytes()` existem para
isso, e `tests/test_protocol.py` trava a propriedade.)

### Campos vizinhos 🚧

| Endereço | `LEN` | Valor | Significado provável |
|----------|-------|-------|----------------------|
| `0x0000` | `02` | `01` | estágio de DPI ativo |
| `0x0002` | `02` | `05` | quantidade de estágios |
| `0x002C`–`0x003F` | `08`/`08`/`04` | — | **cor de cada estágio** (`R G B ck`) |

As cores são o indicador visual do nível de DPI. A ordem foi travada pelo
screenshot do app: estágio 2 = azul (`00 00 ff`) e estágio 3 = verde
(`00 ff 00`) batem sem ambiguidade com os quadradinhos da interface.
Marcados 🚧 porque **nenhuma captura mudou** esses campos ainda — o significado
vem de correlação, não de diff isolado.

## Efeito de DPI ("DPI Effect") — endereço `0x004C` ✅

Isolado em diff limpo: o app reescreve a config inteira, e ao ligar/desligar o
"DPI Effect" **só** este registrador mudou.

```
08 07 00 00 4c 06 01 54 01 54 03 52 00 00 00 00 f5     "Steady" (ligado)
08 07 00 00 4c 02 00 55 00 00 00 00 00 00 00 00 a3     desligado
```

| Valor de `0x004C` | Estado |
|-------------------|--------|
| `01` | Steady (ligado) |
| `00` | desligado |

Ligado, o app escreve três registros de 2 bytes (`0x4C`=`01`, `0x4E`=`01`,
`0x50`=`03`); desligado, escreve só o `0x4C`. Isso indica que os três formam o
**grupo** do efeito — o app tem um slider de *Brightness* logo abaixo do
dropdown. O significado de `0x4E` e `0x50` ainda é 🚧.

O dropdown do app tem outras opções além de "Steady" — faltam capturas delas.

## Handshake 🚧

Antes das escritas, o app manda:

```
08 01 00 00 00 04 62 30 61 58 00 00 00 00 00 00 fd
                  └─ ASCII "b0aX" ─┘
```

As escritas de LED funcionam **sem** ele, então não parece obrigatório. Uma
amostra só — não implementar até entender.

## Status / TODO

- [x] Transporte (Feature Report, interface 1)
- [x] Formato do pacote + checksums — a soma ≡ `0x55` vale **por registro** da
      memória, não só no pacote de 17 bytes
- [x] **Endereçamento de 16 bits** (bytes 3–4 do pacote)
- [x] Cor sólida do LED (`0x00A0`)
- [x] Liga/desliga do LED (efeito `0x04`)
- [x] **Brilho** do LED (byte 5) — validado (50% = `0x32`)
- [x] **Efeitos animados**: Ciclo (`00`, vel `13`) e Respiração (`01`, vel `be`) — validados
- [x] **DPI** (`0x000C`) — 5 estágios × 4 bytes (`X Y 00 ck`), fórmula
      `n = round(DPI × 0,012) − 1` validada com 6 valores conhecidos
- [x] **DPI Effect** (`0x004C`) — `01` = Steady, `00` = desligado
- [ ] Demais opções do dropdown de DPI Effect (só o "Steady" foi capturado)
- [ ] Campos `0x004E`/`0x0050` do grupo do DPI Effect
- [ ] `0x0000` (estágio ativo) e `0x0002` (contagem) — nunca vistos mudando
- [ ] Cores por estágio (`0x002C`) — significado por correlação, falta diff isolado
- [ ] **Polling rate** — candidato em `0x0078` (`09`), sem captura que confirme
- [ ] Botões (`0x0060`–`0x0077`, `01 <bitmask> 00 ck`) — estrutura clara, semântica não
- [ ] Páginas `0x0100`–`0x1981` (macros?) — nunca lidas; a leitura só monta o byte baixo
- [ ] Handshake `08 01 ... "b0aX"` — uma amostra, propósito desconhecido
- [x] **Leitura do estado (nível 2)** do LED — resposta por interrupt IN (Report 09)
- [x] **Velocidade** dos efeitos (byte 4) — slider na GUI (faixa interpolada)
- [ ] Cabo (`FA08`): protocolo mapeado só pelo `FA07` (mas já funciona no cabo)

## Como capturar mais (para mapear novas funções)

```bash
sudo dumpcap -i usbmon0 -a duration:30 -w /tmp/captura.pcapng
sudo chown "$USER": /tmp/captura.pcapng
# mude UMA config no app (na VM) durante os 30s, depois compare os blocos
```
