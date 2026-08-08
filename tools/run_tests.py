#!/usr/bin/env python3
"""Run tests/ without pytest (handy when pytest is not installed).

The project's official runner is still pytest (see pytest.ini and
requirements-dev.txt); this is an emergency shortcut with the same basic
semantics: collect every `test_*` from each `tests/test_*.py` and report failures.

Usage: python3 tools/run_tests.py
"""
import sys
import os
import glob
import traceback
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    passed = failed = 0
    for path in sorted(glob.glob(os.path.join(ROOT, 'tests', 'test_*.py'))):
        spec = importlib.util.spec_from_file_location(
            os.path.basename(path)[:-3], path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:      # the module did not even import
            failed += 1
            print(f"FAIL  {os.path.basename(path)} (did not load)")
            traceback.print_exc()
            continue
        for name in sorted(dir(module)):
            if not name.startswith('test_'):
                continue
            try:
                getattr(module, name)()
                passed += 1
                print(f"PASS  {name}")
            except Exception:
                failed += 1
                print(f"FAIL  {name}")
                traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
