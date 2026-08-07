---
name: captura
description: Captura o tráfego USB do software oficial (rodando em VM Windows) e decodifica o comando de uma função do mouse M711 Pro. É o coração da engenharia reversa deste repo — usbmon + dumpcap pra gravar, tshark pra extrair, diff de blocos pra isolar o que mudou. Use quando for mapear uma função nova (DPI, polling, botão, brilho, efeito) ou confirmar uma existente.
---

# Captura e decodificação de protocolo USB

O software oficial do M711 Pro só roda no Windows. A estratégia é rodá-lo numa **VM (VirtualBox, com USB passthrough do dongle)** e capturar o tráfego **do lado do Linux** com `usbmon` — o kernel do host vê os URBs mesmo com o dispositivo na VM.

## Pré-requisitos (confirme antes)

- Módulo `usbmon` carregado (`sudo modprobe usbmon`).
- `dumpcap`/`tshark` instalados; usuário no grupo `wireshark` **ou** usar `sudo`.
- Mouse ligado no **modo 2.4G (dongle)** — a config **não** vai por cabo nem BT.
- A VM com o app oficial aberto e **detectando** o mouse.
- Regra udev dando acesso ao `/dev/hidraw` (ver README).

## 1. Capturar UMA mudança por vez

O app reescreve a config **inteira** ao aplicar; a única forma de isolar uma função é mudar **um** parâmetro por captura e comparar.

```bash
sudo dumpcap -i usbmon0 -a duration:30 -w /tmp/captura.pcapng
sudo chown "$USER": /tmp/captura.pcapng
```

Durante os 30s, mude **um só** parâmetro no app (ex.: cor pra vermelho puro, ou DPI pra um número redondo). Evite mexer o mouse à toa (reduz ruído).

> 💡 Use **valores conhecidos** (vermelho `FF0000`, DPI `1600`) — facilita achar os bytes.

## 2. Extrair os pacotes de config

Os comandos são control transfers (SET_REPORT) host→receptor. Filtre pelo dispositivo do mouse (bus/addr do `25A7:FA07` — confira com `lsusb`), direção OUT:

```bash
tshark -r /tmp/captura.pcapng \
  -Y 'usb.bus_id==1 && usb.device_address==<ADDR> && usb.endpoint_address.direction==0' \
  -T fields -e frame.number -e usb.data_fragment 2>/dev/null | grep -vE '\t$'
```

Cada pacote tem 17 bytes: `08 07 <endereço16> <tam> <dados...> <checksum>` (ver docs/PROTOCOL.md).

## 3. Separar em blocos e DIFF

Uma "ação" = um bloco de pacotes seguidos. Separe por lacuna de frame e **compare** o bloco antes vs. depois pra achar o(s) byte(s) que mudou:

```bash
awk -F'\t' '{ if (prev && $1-prev>50) print "----- BLOCO -----"; print; prev=$1 }' arquivo.txt
```

O byte que muda entre "valor A" e "valor B" **é** o registrador da função.

## 4. Confirmar com 2+ amostras

**Nunca** conclua com uma amostra só. Capture o mesmo parâmetro em ≥2 valores conhecidos (ex.: cor vermelha E verde) pra confirmar posição e ordem dos bytes. Um único sample gera hipótese, não fato.

## 5. Registrar

Passe o achado pra skill **`protocolo`** (documenta no `docs/PROTOCOL.md`) e depois pra **`coder`** (implementa + teste de byte-match).

## Armadilhas conhecidas

- **Ruído de movimento**: os interrupt-IN do mouse poluem; filtre por control transfers / direção OUT.
- **Ruído de Bluetooth**: se houver headset BT, o áudio gera milhares de pacotes em outro bus — filtre pelo bus/addr do mouse.
- **App reescreve tudo**: sempre diff de blocos, nunca "o pacote com o valor".
- **Device na VM**: pra depois TESTAR o código no Linux, o mouse precisa sair da VM (senão o host não acessa).
