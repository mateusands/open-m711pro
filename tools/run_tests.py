#!/usr/bin/env python3
"""Roda tests/ sem pytest (útil quando o pytest não está instalado).

O runner oficial do repo continua sendo o pytest (ver pytest.ini e
requirements-dev.txt); este é só um atalho de emergência com a mesma semântica
básica: coleta `test_*` de cada `tests/test_*.py` e reporta falhas.

Uso: python3 tools/run_tests.py
"""
import sys
import os
import glob
import traceback
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    ok = falhas = 0
    for path in sorted(glob.glob(os.path.join(ROOT, 'tests', 'test_*.py'))):
        spec = importlib.util.spec_from_file_location(
            os.path.basename(path)[:-3], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for name in sorted(dir(mod)):
            if not name.startswith('test_'):
                continue
            try:
                getattr(mod, name)()
                ok += 1
                print(f"PASS  {name}")
            except Exception:
                falhas += 1
                print(f"FAIL  {name}")
                traceback.print_exc()
    print(f"\n{ok} passaram, {falhas} falharam")
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
