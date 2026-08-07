"""Comunicação com o mouse via hidraw (I/O). Sem dependências externas.

Descobre TODAS as interfaces de config presentes (dongle 2.4G `FA07` e/ou mouse
`FA08`) e envia o comando para todas — a do modo ativo recebe. Reenvia algumas
vezes para vencer o "sono" do mouse wireless.
"""
import os
import glob
import time
import select
import fcntl

from .protocol import (build_color, build_breathing, build_cycle, build_off,
                       build_commit, build_read, SPEED_RESPIRACAO, SPEED_CICLO)
from . import state

EFFECT_NAMES = {0x00: "Ciclo", 0x01: "Respiração", 0x02: "Fixo", 0x04: "Desligado"}
LED_ADDR = 0xA0

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


def send_color(r, g, b, brightness=0xFF):
    vias = send_packet(build_color(r, g, b, brightness=brightness))
    state.save({"effect": "Fixo", "rgb": [r, g, b], "brightness": brightness})
    return vias


def send_breathing(r, g, b, brightness=0xFF, speed=SPEED_RESPIRACAO):
    vias = send_packet(build_breathing(r, g, b, brightness=brightness, speed=speed))
    state.save({"effect": "Respiração", "rgb": [r, g, b], "brightness": brightness, "speed": speed})
    return vias


def send_cycle(r, g, b, brightness=0xFF, speed=SPEED_CICLO):
    vias = send_packet(build_cycle(r, g, b, brightness=brightness, speed=speed))
    state.save({"effect": "Ciclo", "rgb": [r, g, b], "brightness": brightness, "speed": speed})
    return vias


def send_off():
    vias = send_packet(build_off())
    st = state.load()
    st["effect"] = "Desligado"
    state.save(st)
    return vias


# --- Leitura do estado real do hardware (nível 2) ---------------------------
def read_register(addr, length=8, timeout=0.6):
    """Envia a requisição de leitura e captura o response (interrupt IN, Report
    ID 09). Retorna os bytes do report ou None se não veio a tempo."""
    devices = find_devices()
    if not devices:
        raise DeviceNotFound("mouse não encontrado")
    dev, _ = devices[0]
    fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
    try:
        fcntl.ioctl(fd, _HIDIOCSFEATURE(17), bytearray(build_read(addr, length)))
        end = time.monotonic() + timeout
        while True:
            rem = end - time.monotonic()
            if rem <= 0:
                return None
            if not select.select([fd], [], [], rem)[0]:
                return None
            try:
                data = os.read(fd, 64)
            except (BlockingIOError, OSError):
                continue
            if (len(data) >= 12 and data[0] == 0x09 and data[1] == 0x08
                    and data[4] == (addr & 0xFF)):
                return data
    finally:
        os.close(fd)


def read_led_state():
    """Lê o estado atual do LED direto do mouse. Retorna dict (mesmo formato do
    state persistido) ou None se a leitura falhar."""
    try:
        resp = read_register(LED_ADDR, 8)
    except (DeviceNotFound, OSError):
        return None
    if not resp or len(resp) < 12:
        return None
    effect = EFFECT_NAMES.get(resp[6], "Fixo")
    return {"effect": effect, "rgb": [resp[7], resp[8], resp[9]],
            "speed": resp[10], "brightness": resp[11]}
