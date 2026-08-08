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
                       build_commit, build_read, build_dpi_table_bytes,
                       build_dpi_effect, byte_to_dpi, dpi_to_byte,
                       SPEED_RESPIRACAO, SPEED_CICLO, DPI_ADDR, DPI_STAGES,
                       DPI_EFFECT_ADDR, build_buttons, build_media,
                       BUTTON_ADDR, BUTTON_COUNT, BTN_EXTENDED)
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


def _apply(dev_path, pkts):
    """Envia cada pacote (com reenvio) e fecha com UM commit, como o app faz."""
    for pkt in pkts:
        for _ in range(RETRIES):
            _send_feature(dev_path, pkt)
            time.sleep(RETRY_DELAY)
    _send_feature(dev_path, build_commit())


def _mode_label(pid):
    return "2.4G" if pid == 0xFA07 else "cabo"


def send_packets(pkts):
    """Envia a sequência `pkts` a toda interface presente, com um commit no
    final. Retorna as vias que aceitaram (ex.: ['2.4G', 'cabo']). Levanta
    DeviceNotFound se nenhuma aceitou."""
    devices = find_devices()
    if not devices:
        raise DeviceNotFound(
            "mouse não encontrado — verifique o dongle/cabo, a regra udev "
            "(0666) e se a VM não está com o mouse capturado")
    ok = []
    for dev, pid in devices:
        try:
            _apply(dev, pkts)
            ok.append(_mode_label(pid))
        except OSError:
            pass
    if not ok:
        raise DeviceNotFound("nenhuma interface aceitou o comando")
    return ok


def send_packet(pkt):
    """Envia um pacote único (atalho para send_packets)."""
    return send_packets([pkt])


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
def _read_from(dev_path, addr, length, timeout):
    """Tenta ler `addr` por uma interface. Retorna o report 09 ou None."""
    fd = os.open(dev_path, os.O_RDWR | os.O_NONBLOCK)
    try:
        for _ in range(RETRIES):        # reenvia: o 1o às vezes só acorda o mouse
            fcntl.ioctl(fd, _HIDIOCSFEATURE(17), bytearray(build_read(addr, length)))
            time.sleep(RETRY_DELAY)
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
            # confere os DOIS bytes de endereço: só o baixo deixaria uma
            # resposta da página 0 passar por outra página
            if (len(data) >= 12 and data[0] == 0x09 and data[1] == 0x08
                    and data[3] == ((addr >> 8) & 0xFF)
                    and data[4] == (addr & 0xFF)):
                return data
    finally:
        os.close(fd)


def read_register(addr, length=8, timeout=0.6):
    """Envia a requisição de leitura e captura o response (interrupt IN, Report
    ID 09). Retorna os bytes do report ou None se nenhuma interface respondeu.

    Tenta TODAS as interfaces presentes: com dongle e cabo ligados ao mesmo
    tempo, quem responde é o nó do mouse (FA08), não necessariamente o primeiro
    da lista — fixar `devices[0]` fazia a leitura falhar em silêncio.
    """
    devices = find_devices()
    if not devices:
        raise DeviceNotFound("mouse não encontrado")
    for dev, _ in devices:
        try:
            resp = _read_from(dev, addr, length, timeout)
        except OSError:
            continue
        if resp:
            return resp
    return None


def read_dpi_bytes():
    """Lê os BYTES crus dos 5 estágios de DPI. Retorna [b1..b5] ou None.

    Três leituras nas mesmas formas que o app usa para escrever: 0x0C (LEN 8,
    estágios 1–2), 0x14 (LEN 8, estágios 3–4) e 0x1C (LEN 4, estágio 5).

    Devolve BYTES, não DPI, de propósito: quem só quer mudar um estágio precisa
    reescrever os outros quatro **exatamente** como estavam, e a conversão
    byte -> DPI -> byte não é identidade acima de 0xBD.
    """
    out = []
    for addr, ln in ((DPI_ADDR, 8), (DPI_ADDR + 8, 8), (DPI_ADDR + 16, 4)):
        resp = read_register(addr, ln)
        if not resp or len(resp) < 6 + ln:
            return None
        data = resp[6:6 + ln]
        out += [data[i] for i in range(0, ln, 4)]
    return out


def read_dpi_table():
    """Lê os 5 estágios de DPI do hardware, em DPI. Retorna lista ou None."""
    raw = read_dpi_bytes()
    return None if raw is None else [byte_to_dpi(b) for b in raw]


def send_dpi_bytes(values):
    """Escreve os 5 estágios a partir dos bytes crus do registrador."""
    vias = send_packets(build_dpi_table_bytes(values))
    state.save({**state.load(), "dpi_stages": [byte_to_dpi(b) for b in values]})
    return vias


def send_dpi_table(stages):
    """Escreve os 5 estágios de uma vez, a partir de valores em DPI."""
    return send_dpi_bytes([dpi_to_byte(d) for d in stages])


def send_dpi(stage, dpi):
    """Muda UM estágio (1 a 5) preservando os outros byte a byte.

    A tabela é escrita inteira pelo protocolo, então lemos a atual antes. Se a
    leitura falhar, abortamos: reescrever os outros quatro estágios com valor
    chutado é justamente o que a regra de ouro do repo proíbe.

    Retorna (vias, tabela_em_dpi) — a tabela **resultante**, já quantizada pelo
    passo do hardware, e não o que foi pedido.
    """
    if not 1 <= stage <= DPI_STAGES:
        raise ValueError(f"estágio deve estar entre 1 e {DPI_STAGES}")
    raw = read_dpi_bytes()
    if raw is None:
        raise DeviceNotFound(
            "não consegui ler a tabela de DPI atual — sem ela eu reescreveria "
            "os outros estágios com chute. Confira o dongle e tente de novo.")
    raw[stage - 1] = dpi_to_byte(dpi)
    vias = send_dpi_bytes(raw)
    return vias, [byte_to_dpi(b) for b in raw]


def send_dpi_all(dpi):
    """Aplica o MESMO DPI aos 5 estágios — o mouse passa a ter um DPI só.

    Com todos os estágios iguais, o botão de DPI do mouse continua ciclando mas
    não muda mais a sensibilidade. Retorna (vias, dpi_resultante).
    """
    b = dpi_to_byte(dpi)
    return send_dpi_bytes([b] * DPI_STAGES), byte_to_dpi(b)


def read_buttons():
    """Lê os 16 registros de botão. Retorna [(TIPO,P1,P2), ...] ou None.

    Devolve os bytes crus para que quem muda um botão possa reescrever os
    outros quinze exatamente como estavam — inclusive tipos que ainda não
    sabemos interpretar.
    """
    out = []
    for i in range(0, BUTTON_COUNT, 2):
        resp = read_register(BUTTON_ADDR + 4 * i, 8)
        if not resp or len(resp) < 14:
            return None
        d = resp[6:14]
        out.append(tuple(d[0:3]))
        out.append(tuple(d[4:7]))
    return out


def send_buttons(actions):
    """Escreve a tabela de botões inteira (16 ações)."""
    return send_packets(build_buttons(actions))


def _tabela_atual():
    atual = read_buttons()
    if atual is None:
        raise DeviceNotFound(
            "não consegui ler a tabela de botões — sem ela eu reescreveria os "
            "outros botões com chute. Confira o dongle e tente de novo.")
    return atual


def send_button(index, action):
    """Muda UM botão (índice 0–15) preservando os outros byte a byte."""
    if not 0 <= index < BUTTON_COUNT:
        raise ValueError(f"índice de botão deve estar entre 0 e {BUTTON_COUNT - 1}")
    nova = _tabela_atual()
    nova[index] = tuple(action)
    return send_buttons(nova), nova


def send_media(index, usage):
    """Atribui uma tecla de multimídia ao botão `index`.

    Grava o slot estendido primeiro e só então a tabela de botões, na mesma
    ordem em que o app oficial faz.
    """
    if not 0 <= index < BUTTON_COUNT:
        raise ValueError(f"índice de botão deve estar entre 0 e {BUTTON_COUNT - 1}")
    nova = _tabela_atual()
    nova[index] = BTN_EXTENDED
    vias = send_packets([build_media(index, usage)] + build_buttons(nova))
    return vias, nova


def read_dpi_effect():
    """Lê o grupo do DPI Effect. Retorna (ligado, (b_0x4E, b_0x50)) ou None."""
    resp = read_register(DPI_EFFECT_ADDR, 6)
    if not resp or len(resp) < 12:
        return None
    d = resp[6:12]                      # 0x4C ck | 0x4E ck | 0x50 ck
    return bool(d[0]), (d[2], d[4])


def send_dpi_effect(on):
    """Liga (Steady) ou desliga o LED indicador de nível de DPI.

    Ao ligar, lê antes os campos 0x4E/0x50 — ainda não decodificados — e os
    devolve intactos, em vez de sobrescrevê-los com os valores da captura.
    """
    if on:
        atual = read_dpi_effect()
        if atual is None:
            raise DeviceNotFound(
                "não consegui ler o estado do DPI Effect — sem ele eu "
                "sobrescreveria os campos 0x4E/0x50, que ainda não foram "
                "decodificados. Confira o dongle e tente de novo.")
        pkt = build_dpi_effect(True, tail=atual[1])
    else:
        pkt = build_dpi_effect(False)
    vias = send_packets([pkt])
    state.save({**state.load(), "dpi_effect": bool(on)})
    return vias


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
