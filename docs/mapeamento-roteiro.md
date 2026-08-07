# Roteiro de mapeamento em lote

Objetivo: numa **única captura**, mudar **várias** configurações no app oficial
(na VM), em **ordem conhecida** e com **pausas**, para decodificar tudo de uma vez.

## Como funciona

O app reescreve a config a cada mudança → cada ação vira um **bloco** no tráfego.
A pausa entre ações separa os blocos; a ordem conhecida deixa cada bloco rotulado
("bloco 5 = DPI 800"). Aí é só fazer o diff de blocos vizinhos e decodificar.

## Preparação

- Mouse no **modo 2.4G (dongle)**, app oficial aberto **na VM** detectando o mouse.
- `usbmon` carregado; terminal pronto.

## Iniciar a captura (5 min)

```bash
sudo dumpcap -i usbmon0 -a duration:300 -w /tmp/mapa.pcapng
sudo chown "$USER": /tmp/mapa.pcapng
```

## Regras de ouro

1. Faça as ações **na ordem exata** abaixo.
2. **Pause ~3 segundos** depois de cada ação (deixe o app "assentar").
3. Se o app tiver botão **"Aplicar"**, clique após cada mudança.
4. **Não mexa o mouse** sem necessidade (reduz ruído).
5. Se pular ou errar uma ação, **anote** qual — me avise depois.

## Ações (siga na ordem, pausando entre cada)

### Iluminação
1. Efeito **Fixo**, cor **vermelho puro** (R255 G0 B0)
2. Cor **verde puro** (R0 G255 B0)
3. Cor **azul puro** (R0 G0 B255)
4. Brilho **100%**
5. Brilho **50%**
6. Brilho **0%** (mínimo)
7. Brilho **100%** de novo
8. Efeito **Respiração**
9. Efeito **Ciclo**
10. Efeito **Fixo** (volta)
11. **Desligar** a iluminação

### DPI
12. DPI **800**
13. DPI **1600**
14. DPI **3200**

### Taxa de relatório (polling)
15. Polling **1000 Hz**
16. Polling **500 Hz**
17. Polling **125 Hz**

### (Opcional) Botões
18. Remapeie **um** botão para uma função diferente (anote qual botão e função)

## Nível 2 — ler o estado do hardware (opcional, mas importante)

Para o app **abrir refletindo o estado real** do mouse (não só o que ele mesmo
setou), precisamos ver o que o app oficial **lê** ao abrir. Numa captura à parte:

1. **Feche** o app oficial.
2. Inicie a captura (`dumpcap ... -a duration:30`).
3. **Abra** o app oficial (ele vai consultar o mouse — GET reports).
4. Pare e me mande. Eu decodifico como o mouse **reporta** cor/efeito/DPI atuais.

## Ao terminar

Pare (a captura fecha sozinha em 5 min) e me avise o caminho `/tmp/mapa.pcapng`.
Diga também se pulou/trocou alguma ação. Eu decodifico bloco a bloco e implemento
tudo (código + `docs/PROTOCOL.md`) de uma vez.
