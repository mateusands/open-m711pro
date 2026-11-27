"""Interface language: English (the source strings) and Brazilian Portuguese.

Pure stdlib, no Qt: the English text IS the key, so an untranslated string
simply shows in English instead of breaking. `tr("Stage {n}", n=2)` formats
after translating, so placeholders stay in the translation.

Display only. Values that drive behaviour — effect names handed to
device.sender_for, action tuples — never go through here; the UI keeps them
as item data and translates only what is painted. (A renamed effect once made
the lighting combo send nothing at all.)
"""
import os

from ..core import state

LANGUAGES = {"en": "EN", "pt": "PT-BR"}
DEFAULT = "en"
_current = None


def _from_environment():
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = os.environ.get(var, "")
        if value:
            return "pt" if value.lower().startswith("pt") else DEFAULT
    return DEFAULT


def language():
    """The active language: the saved choice, else the system locale."""
    global _current
    if _current is None:
        saved = state.load().get("language")
        _current = saved if saved in LANGUAGES else _from_environment()
    return _current


def set_language(code, persist=True):
    global _current
    if code not in LANGUAGES:
        raise ValueError(f"unknown language {code!r}")
    _current = code
    if persist:
        state.save({**state.load(), "language": code})


def tr(text, **values):
    if language() == "pt":
        text = PT.get(text, text)
    return text.format(**values) if values else text


def tr_error(exc):
    """A device-layer error message in the interface language.

    The core stays English (it is also the CLI's voice); the messages a
    first-time user actually meets are recognised here by their stable start.
    """
    message = str(exc)
    if language() != "pt":
        return message
    for prefix, translated in ERRORS_PT:
        if message.startswith(prefix):
            nodes = message[message.find("(") + 1:message.find(")")] \
                if "(" in message else ""
            return translated.format(nodes=nodes)
    return message


ERRORS_PT = [
    ("the mouse was found",
     "o mouse foi encontrado ({nodes}), mas este usuário não tem permissão para "
     "abri-lo — a regra udev não está instalada ou não foi aplicada. Rode 'open-m711pro setup' (num "
     "clone: 'python3 main.py setup' ou 'sudo sh packaging/install.sh') e "
     "reconecte o dongle."),
    ("mouse not found",
     "mouse não encontrado — confira se o dongle está conectado, o mouse ligado "
     "e se nenhuma máquina virtual capturou o dispositivo."),
    ("no interface accepted the command",
     "nenhuma interface aceitou o comando."),
    ("could not read",
     "não foi possível ler o estado atual do mouse — sem ele os outros valores "
     "seriam regravados no chute. Confira o dongle e tente de novo."),
]


PT = {
    # navigation and shell
    "Lighting": "Iluminação",
    "Sensitivity (DPI)": "Sensibilidade (DPI)",
    "Buttons": "Botões",
    "Ready.": "Pronto.",
    "Language": "Idioma",
    "Read from mouse": "Ler do mouse",
    "Error: {error}": "Erro: {error}",
    "{what} — via {routes}": "{what} — via {routes}",

    # lighting
    "LIGHTING": "ILUMINAÇÃO",
    "EFFECT": "EFEITO",
    "Steady": "Fixo",
    "Breathing": "Respiração",
    "Cycle": "Ciclo",
    "Off": "Desligado",
    "BRIGHTNESS": "BRILHO",
    "SPEED (Slow -> Fast)": "VELOCIDADE (lenta -> rápida)",
    "Custom colour…": "Outra cor…",
    "Pick a colour": "Escolha uma cor",
    "Lighting is off.": "Iluminação desligada.",
    "LED off": "LED desligado",
    "{effect} {colour} ({pct}%)": "{effect} {colour} ({pct}%)",

    # DPI
    "SENSITIVITY (DPI)": "SENSIBILIDADE (DPI)",
    "MODE": "MODO",
    "Single DPI": "DPI único",
    "5 stages": "5 estágios",
    "Independent X / Y axes": "Eixos X / Y independentes",
    "Type a value and press Enter, drag the slider, or pick a preset. The mouse "
    "works in steps of ~{step} DPI: values are shown the way the official app "
    "shows them, with the real one beside them when it differs (700 is really "
    "≈667).":
        "Digite um valor e aperte Enter, arraste o controle ou escolha um atalho. "
        "O mouse trabalha em passos de ~{step} DPI: os valores aparecem como no "
        "app oficial, com o valor real ao lado quando é diferente (700 na verdade "
        "é ≈667).",
    "DPI STAGE INDICATOR": "INDICADOR DE ESTÁGIO DE DPI",
    "Light the LED in the active stage's colour (DPI Effect)":
        "Acender o LED na cor do estágio ativo (DPI Effect)",
    "POLLING RATE (Hz)": "TAXA DE POLLING (Hz)",
    "≈{real} real": "≈{real} real",
    "The mouse stores DPI in steps of ~83; this is the value it really holds. "
    "The official app shows the rounded number.":
        "O mouse guarda o DPI em passos de ~83; este é o valor que ele realmente "
        "usa. O app oficial mostra o número arredondado.",
    "Stage colour — the LED shows it when this stage is active":
        "Cor do estágio — o LED mostra esta cor quando o estágio está ativo",
    "Stage {n} colour": "Cor do estágio {n}",
    "Stage {n} colour = {colour}": "Cor do estágio {n} = {colour}",
    "The five stages still differ ({current}). Confirm a value above to make "
    "them all equal.":
        "Os cinco estágios ainda são diferentes ({current}). Confirme um valor "
        "acima para deixar todos iguais.",
    "All five stages are equal — the mouse's DPI button cycles without changing "
    "the sensitivity.":
        "Os cinco estágios são iguais — o botão de DPI do mouse alterna entre "
        "eles sem mudar a sensibilidade.",
    "Could not read the DPI — did the mouse answer?":
        "Não foi possível ler o DPI — o mouse respondeu?",
    "DPI read from the mouse — the polling rate did not answer.":
        "DPI lido do mouse — a taxa de polling não respondeu.",
    "DPI read from the mouse.": "DPI lido do mouse.",
    "DPI = {dpi} on all five stages": "DPI = {dpi} nos cinco estágios",
    "Stage {n} = {dpi}": "Estágio {n} = {dpi}",
    "Stage {n} = X {x} / Y {y}": "Estágio {n} = X {x} / Y {y}",
    "DPI Effect on": "DPI Effect ligado",
    "DPI Effect off": "DPI Effect desligado",
    "Polling rate = {hz} Hz": "Taxa de polling = {hz} Hz",
    "unknown ({raw})": "desconhecido ({raw})",

    # buttons
    "BUTTONS": "BOTÕES",
    "Button {n}": "Botão {n}",
    "left click": "clique esquerdo",
    "right click": "clique direito",
    "wheel": "roda",
    "side": "lateral",
    "top": "topo",
    "Click a number on the mouse to jump to its row. These are the eight buttons "
    "the mouse actually has, numbered the way the official app numbers them. The "
    "register table has sixteen slots, but the other eight fire nothing on this "
    "model — they are preserved untouched on every write and simply not offered "
    "here.":
        "Clique num número do mouse para ir até a linha dele. Estes são os oito "
        "botões que o mouse realmente tem, numerados como no app oficial. A tabela "
        "interna tem dezesseis posições, mas as outras oito não fazem nada neste "
        "modelo — são preservadas intactas a cada gravação e apenas não aparecem "
        "aqui.",
    "An action this app cannot build is shown as its raw bytes and cannot be "
    "selected — the byte is preserved instead of being guessed at.":
        "Uma ação que este app não sabe montar aparece com os bytes crus e não "
        "pode ser escolhida — o byte é preservado em vez de ser adivinhado.",
    "Could not read the buttons — did the mouse answer?":
        "Não foi possível ler os botões — o mouse respondeu?",
    "Buttons read from the mouse.": "Botões lidos do mouse.",
    "Button {n} = {action}": "Botão {n} = {action}",
    "Button {n} = media '{key}'": "Botão {n} = mídia '{key}'",
    "Left click": "Clique esquerdo",
    "Right click": "Clique direito",
    "Middle click": "Clique do meio",
    "Back": "Voltar",
    "Forward": "Avançar",
    "DPI up": "DPI +",
    "DPI down": "DPI −",
    "DPI cycle": "Alternar DPI",
    "Three click": "Três cliques",
    "Fire key": "Tecla de disparo",
    "RGB on/off": "Liga/desliga RGB",
    "Polling rate switch": "Alternar taxa de polling",
    "Multimedia key": "Tecla multimídia",
    "Disabled": "Desativado",
    "Play / pause": "Tocar / pausar",
    "Next track": "Próxima faixa",
    "Previous track": "Faixa anterior",
    "Mute": "Mudo",
    "Stop": "Parar",
    "Volume up": "Volume +",
    "Volume down": "Volume −",
    "unknown slot": "desconhecido",
    "Factory reset (not assignable here)":
        "Reset de fábrica (não atribuível aqui)",
    "unknown (usage {usage})": "desconhecido (código {usage})",
}
