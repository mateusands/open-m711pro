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
08 07 <ADDR_HI> <ADDR_LO> <LEN> <DADOS...> <padding> <CHECKSUM>
│  │  └──────┬──────┘     │     └── até LEN bytes de dados
│  │         │            └── quantidade de bytes de dados (0x08, 0x04, 0x02...)
│  │         └── endereço de 16 bits na memória de config do mouse
│  └── opcode: 0x07 = escrever ; 0x04 = aplicar/commit ; 0x08 = limpar região
└── Report ID (0x08)
```

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

## Status / TODO

- [x] Transporte (Feature Report, interface 1)
- [x] Formato do pacote + checksum externo (soma ≡ 0x55)
- [x] Checksum interno do registrador `0x00A0` (soma dos dados ≡ 0x355)
- [x] Cor sólida do LED (`0x00A0`, modo `0x02`)
- [x] Liga/desliga do LED (modo `0x04`) — confirmado via checksum interno
- [ ] Confirmar cores mistas (R+G+B ≠ 0xFF) no hardware — só testamos primárias
- [ ] Confirmar o envio pela via cabo (`FA08`) — protocolo mapeado só pelo `FA07`
- [ ] Brilho / efeito (`96 FF` do registrador `0x00A0`)
- [ ] Mapear DPI, polling rate, botões e macros (outras regiões de memória)
- [ ] Necessidade real do commit (`0x04`) por escrita

## Como capturar mais (para mapear novas funções)

```bash
sudo dumpcap -i usbmon0 -a duration:30 -w /tmp/captura.pcapng
sudo chown "$USER": /tmp/captura.pcapng
# mude UMA config no app (na VM) durante os 30s, depois compare os blocos
```
