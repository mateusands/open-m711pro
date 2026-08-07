#!/usr/bin/env python3
"""Dump da memória de configuração do mouse — SOMENTE LEITURA.

Varre o espaço de endereços com a requisição de leitura já validada
(`protocol.build_read`, opcode 0x08) e imprime o que o mouse responde.
Nenhum byte de ESCRITA é enviado: o opcode 0x07 (escrever) e o 0x04 (commit)
não são usados aqui, então o dump não altera estado do hardware.

Endereços são de 16 bits e aceitos em hex (sem 0x): a config principal vive em
0x0000–0x00A8, mas o app oficial varre até 0x1981.

Uso:
    python3 tools/dump_config.py                    # varre 0x0000..0x00F8
    python3 tools/dump_config.py > /tmp/dpi-800.txt
    python3 tools/dump_config.py --addr 0C          # lê um endereço só
    python3 tools/dump_config.py --start 0100 --end 01F8   # página 1

Fluxo de descoberta (ver docs/roteiro-dpi.md):
    1. app na VM: DPI = 800   → solta o mouse pro host → dump > /tmp/dpi-800.txt
    2. app na VM: DPI = 1600  → solta o mouse pro host → dump > /tmp/dpi-1600.txt
    3. diff -u /tmp/dpi-800.txt /tmp/dpi-1600.txt
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from m711pro.core import device  # noqa: E402


def dump(addr, length=8):
    """Retorna (bytes_de_dados, report_cru) ou (None, None) se não respondeu."""
    try:
        resp = device.read_register(addr, length)
    except (device.DeviceNotFound, OSError) as e:
        raise SystemExit(f"Erro: {e}")
    if not resp:
        return None, None
    return resp[6:6 + length], resp


def fmt(data):
    return ' '.join(f"{b:02x}" for b in data)


def main(argv):
    start, end, step, length = 0x0000, 0x00F8, 0x08, 0x08
    only = None
    width = 2               # dígitos hex no rótulo de endereço
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--addr':
            only = int(argv[i + 1], 16); i += 2
        elif a == '--start':
            start = int(argv[i + 1], 16); i += 2
        elif a == '--end':
            end = int(argv[i + 1], 16); i += 2
        elif a == '--step':
            step = int(argv[i + 1], 0); i += 2
        elif a == '--len':
            length = int(argv[i + 1], 0); i += 2
        else:
            raise SystemExit(__doc__)

    addrs = [only] if only is not None else range(start, end + 1, step)
    if max(addrs) > 0xFF:
        width = 4
    if not device.find_devices():
        raise SystemExit(
            "mouse não encontrado — o dongle está no host (não na VM)? "
            "confira a regra udev e o modo 2.4G.")

    quiet = 0
    for addr in addrs:
        data, _ = dump(addr, length)
        if data is None:
            print(f"{addr:0{width}X}: <sem resposta>")
            quiet += 1
            continue
        print(f"{addr:0{width}X}: {fmt(data)}")
    if quiet:
        print(f"# {quiet} endereço(s) sem resposta", file=sys.stderr)


if __name__ == '__main__':
    main(sys.argv[1:])
