"""The check()/raises() helpers every suite uses: plain scripts, no pytest.

A suite imports this first. It puts the repo on sys.path and points the XDG
folders at a throwaway one, so no test reads or writes the real settings.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_scratch = tempfile.mkdtemp(prefix='tscmanager-test-')
os.environ['XDG_CONFIG_HOME'] = os.path.join(_scratch, 'config')
os.environ['XDG_CACHE_HOME'] = os.path.join(_scratch, 'cache')
atexit.register(shutil.rmtree, _scratch, True)

failures = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name
          + ((" -- " + repr(extra)) if extra != "" and not cond else ""))
    if not cond:
        failures.append(name)


def raises(exc, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc:
        return True
    return False


def finish():
    print(f"\n{len(failures)} failure(s)" if failures else "\nall passed")
    sys.exit(1 if failures else 0)
