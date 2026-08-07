"""Comunicação com o mouse via hidraw (I/O). Sem dependências externas.

Descobre TODAS as interfaces de config presentes (dongle 2.4G `FA07` e/ou mouse
`FA08`) e envia o comando para todas — a do modo ativo recebe. Reenvia algumas
vezes para vencer o "sono" do mouse wireless.
"""
import os
import glob
import time
import fcntl

from .protocol import build_color, build_off, build_commit

VID = 0x25A7
PIDS = [0xFA07, 0xFA08]        # FA07 = receptor 2.4G ; FA08 = mouse (cabo/BT)
TARGET_INTERFACE = 1

RETRIES = 4                    # o 1o comando às vezes só acorda o mouse
RETRY_DELAY = 0.02            # segundos entre reenvios


class DeviceNotFound(Exception):
    """Nenhuma interface de config acessível aceitou o comando."""


def _IOC(direction, typ, nr, size):
    return (direction << 30) | (size << 16) | (typ << 8) | nr


def _HIDIOCSFEATURE(size):
    return _IOC(1 | 2, ord('H'), 0x06, size)     # _IOC_WRITE|_IOC_READ


def find_devices():
    """Lista as interfaces de config presentes: [(dev_path, pid), ...]."""
    found = []
    for pid in PIDS:
        for node in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
            name = os.path.basename(node)
            try:
                uevent = open(os.path.join(node, 'device', 'uevent')).read().upper()
            except OSError:
                continue
            if f"{VID:08X}" not in uevent or f"{pid:08X}" not in uevent:
                continue
            p = os.path.realpath(os.path.join(node, 'device'))
            iface = None
            for _ in range(6):
                bi = os.path.join(p, 'bInterfaceNumber')
                if os.path.exists(bi):
                    try:
                        iface = int(open(bi).read().strip(), 16)
                    except ValueError:
                        iface = None
                    break
                p = os.path.dirname(p)
            if iface == TARGET_INTERFACE:
                found.append((f"/dev/{name}", pid))
    return found


def _send_feature(dev_path, data):
    fd = os.open(dev_path, os.O_RDWR)
    try:
        fcntl.ioctl(fd, _HIDIOCSFEATURE(len(data)), bytearray(data))
    finally:
        os.close(fd)


def _apply(dev_path, pkt):
    for _ in range(RETRIES):
        _send_feature(dev_path, pkt)
        time.sleep(RETRY_DELAY)
    _send_feature(dev_path, build_commit())


def _mode_label(pid):
    return "2.4G" if pid == 0xFA07 else "cabo"


def send_packet(pkt):
    """Envia `pkt` a toda interface presente. Retorna as vias que aceitaram
    (ex.: ['2.4G', 'cabo']). Levanta DeviceNotFound se nenhuma aceitou."""
    devices = find_devices()
    if not devices:
        raise DeviceNotFound(
            "mouse não encontrado — verifique o dongle/cabo, a regra udev "
            "(0666) e se a VM não está com o mouse capturado")
    ok = []
    for dev, pid in devices:
        try:
            _apply(dev, pkt)
            ok.append(_mode_label(pid))
        except OSError:
            pass
    if not ok:
        raise DeviceNotFound("nenhuma interface aceitou o comando")
    return ok


def send_color(r, g, b):
    return send_packet(build_color(r, g, b))


def send_off():
    return send_packet(build_off())
