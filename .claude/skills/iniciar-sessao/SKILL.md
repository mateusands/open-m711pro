---
name: iniciar-sessao
description: Inicializa a sessão de trabalho no open-m711pro — lê os docs do repo (README.md + docs/PROTOCOL.md) em modo somente leitura, internaliza o estado atual da engenharia reversa e confirma o alinhamento de escopo antes de qualquer código. Use no começo de cada sessão.
---

# Inicialização de Sessão

A fonte da verdade deste projeto são os **próprios docs do repositório** — não há vault externo. Antes de qualquer ação, leia e assimile, em ordem:

1. **README.md** — objetivo do projeto, estado atual (tabela de funções), requisitos (regra udev, dongle 2.4G) e roadmap.
2. **docs/PROTOCOL.md** — o mapa da engenharia reversa: identificação do dispositivo, camada de transporte (Feature Report, interface 1), formato do pacote de 17 bytes, o checksum (soma ≡ 0x55 mod 256), os registradores já decodificados e a seção **Status / TODO**.
3. **O código** (`m711led.py` e o que mais existir) — confirme que ele bate com o que o PROTOCOL.md descreve.

## Modo somente leitura

Nesta etapa é **proibido** editar código, criar ou apagar arquivos. O objetivo é só carregar contexto e verificar alinhamento.

## Convenções do repo a internalizar

- **Python puro (stdlib)** — sem dependências externas; acesso ao hardware via `hidraw` + `ioctl`.
- Todo byte enviado ao mouse tem que ter **origem numa captura real** (nunca chute mandado pro hardware).
- Checksum: `(0x55 - soma_dos_16_primeiros_bytes) & 0xFF`.
- Alvo dos comandos: receptor `25A7:FA07`, **interface 1**, Feature Report ID `0x08`.

## O que responder ao usuário

Retorno **curto**: (1) confirme que leu os docs, (2) diga em uma frase o **estado atual** do protocolo (o que já está decodificado vs. o que está na fila do TODO), e (3) pergunte/confirme o foco da sessão. Sem codar ainda.
