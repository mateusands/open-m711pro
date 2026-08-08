"""Named colours (for the CLI) and the swatch palette (for the GUI)."""
import colorsys

# Colours by name, used by the CLI. Portuguese aliases are kept so the
# original commands keep working.
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
    """An image-editor style grid: a greyscale row plus hue rows at several
    brightness and saturation levels. Returns a list of rows, each row a list of
    (r, g, b) tuples."""
    rows = []

    # Row 1 — greyscale (black -> white)
    rows.append([_hsv(0, 0, i / (hues - 1)) for i in range(hues)])

    # Full-saturation hue rows at decreasing brightness
    for v in (1.0, 0.75, 0.5):
        rows.append([_hsv(i / hues, 1.0, v) for i in range(hues)])

    # Pastel row (low saturation)
    rows.append([_hsv(i / hues, 0.4, 1.0) for i in range(hues)])

    return rows
