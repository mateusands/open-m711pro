---
name: protocolo
description: Documenta uma descoberta de engenharia reversa no docs/PROTOCOL.md com o formato padrão do repo, exigindo evidência de captura e marcando o nível de confiança. Use depois da skill `captura`, quando um registrador/função novo foi decodificado e precisa virar documentação (a fonte da verdade que a skill `coder` implementa).
---

# Registro de protocolo

O `docs/PROTOCOL.md` é a **fonte da verdade** do que o mouse entende. Toda linha de código que manda bytes pro hardware deriva daqui. Documentar mal = mandar chute pro hardware depois.

## Regra de evidência

- **Todo byte documentado precisa vir de captura real.** Sem `.pcapng` de origem, não entra.
- **≥2 amostras** pra afirmar o significado de um byte (ex.: cor confirmada com vermelho *e* verde). Com 1 amostra só, documente como **🚧 tentativo** e diga o que falta capturar.
- Prefira **valores conhecidos** (FF0000, DPI 1600) — a evidência fica auto-explicativa.

## O que registrar (formato)

Para um registrador/função novo, adicione uma seção com:

1. **Endereço** e opcode (ex.: escrita `0x07` no endereço `0x00A0`).
2. **Layout dos bytes** anotado:
   ```
   08 07 00 00 A0 07 | 02 | RR GG BB | 96 FF BF | ... | <cksum>
                       │    └─R─G─B┘
                       └── modo
   ```
3. **Tabela valor→bytes** com as capturas que provam:
   | Valor no app | Bytes |
   |--------------|-------|
   | Vermelho     | `FF 00 00` |
   | Verde        | `00 FF 00` |
4. **Confiança**: ✅ confirmado (≥2 amostras) ou 🚧 tentativo (1 amostra / faltam casos).
5. Atualize a seção **Status / TODO** (marque o item, adicione os novos).

## Sincronize com o código

Um registrador documentado vira, no código:
- uma função `build_<coisa>()` que monta o pacote;
- um **teste de byte-match** que prova que a função reproduz a captura conhecida (é a rede de segurança contra regressão — ver skill `coder`).

Se o PROTOCOL.md e o código divergirem, um dos dois está errado — pare e reconcilie.

## Checksum — sempre reconfira

Ao documentar um pacote novo, valide o checksum: soma dos 17 bytes ≡ `0x55` (mod 256). Se não fechar, ou o pacote foi lido errado, ou a regra do checksum tem exceção que precisa ser investigada.
