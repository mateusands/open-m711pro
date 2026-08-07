"""Cores nomeadas (para a CLI) e a paleta de swatches (para a GUI)."""
import colorsys

# Cores por nome — usadas na CLI (PT e EN).
NAMED = {
    'red': (255, 0, 0), 'vermelho': (255, 0, 0),
    'green': (0, 255, 0), 'verde': (0, 255, 0),
    'blue': (0, 0, 255), 'azul': (0, 0, 255),
    'white': (255, 255, 255), 'branco': (255, 255, 255),
    'yellow': (255, 255, 0), 'amarelo': (255, 255, 0),
    'cyan': (0, 255, 255), 'ciano': (0, 255, 255),
    'magenta': (255, 0, 255), 'rosa': (255, 0, 255),
    'orange': (255, 128, 0), 'laranja': (255, 128, 0),
    'purple': (128, 0, 255), 'roxo': (128, 0, 255),
}


def _hsv(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def palette(hues=16):
    """Grade de cores estilo editor de imagem: linhas de tons de cinza + matizes
    em vários brilhos/saturações. Retorna lista de linhas; cada linha é uma lista
    de tuplas (r, g, b)."""
    rows = []

    # Linha 1 — escala de cinza (preto -> branco)
    rows.append([_hsv(0, 0, i / (hues - 1)) for i in range(hues)])

    # Linhas de matiz cheias, variando o brilho
    for v in (1.0, 0.75, 0.5):
        rows.append([_hsv(i / hues, 1.0, v) for i in range(hues)])

    # Linha pastel (saturação baixa)
    rows.append([_hsv(i / hues, 0.4, 1.0) for i in range(hues)])

    return rows
