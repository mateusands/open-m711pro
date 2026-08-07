"""Persistência do último estado definido pelo app (nível 1 de "estado atual").

Guarda o que ESTE app aplicou por último (efeito + cor), para reabrir refletindo
o estado real quando o app foi a última coisa a mexer no mouse. Ler o estado
direto do hardware (nível 2) depende de engenharia reversa da leitura — ver
docs/PROTOCOL.md / docs/mapeamento-roteiro.md.
"""
import os
import json


def _path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "open-m711pro", "state.json")


def load():
    """Retorna o estado salvo como dict (vazio se não houver / erro)."""
    try:
        with open(_path()) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(state):
    """Persiste `state` (dict). Silencioso em caso de erro de escrita."""
    p = _path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump(state, f)
    except OSError:
        pass
