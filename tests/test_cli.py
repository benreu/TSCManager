"""tscmanager.py --probe, against the fake printer: it runs from end to end,
shows each raw reply, and leaves no test file behind."""
import subprocess
import sys

from _check import ROOT, check, finish
from fake_printer import FakePrinter

fake = FakePrinter()
try:
    run = subprocess.run(
        [sys.executable, str(ROOT / 'tscmanager.py'), '--probe',
         f'127.0.0.1:{fake.port}', '--probe-write', '--probe-wait', '0.4'],
        capture_output=True, text=True, timeout=120)
    out = run.stdout
    check("the probe runs to the end", run.returncode == 0,
          run.stderr[-800:])
    check("it shows ~!T's raw reply and what was parsed from it",
          "b'TE210\\r'" in out and "parsed: 'TE210'" in out, out[:600])
    check("it shows the GETSETTING$ answers parsed by tag",
          "'dpi': '203'" in out)
    check("it stored every test file, in DRAM and in flash",
          all(f'DOWNLOAD {where} {name}' in fake.received
              for where, name in (('dram', 'PROBE.BMP'),
                                  ('dram', 'probe2.bmp'),
                                  ('dram', 'PROBELONGNAME.BMP'),
                                  ('flash', 'PROBEF.BMP'),
                                  ('dram', 'PROBEG.BMP'),
                                  ('dram', 'PROBE.PNG'))), fake.received)
    check("it printed its test labels",
          len(fake.labels) >= 2
          and any('PUTPNG 160,30,"PROBE.PNG"' in l for l in fake.labels[-1]),
          fake.labels)
    check("and deleted every file it stored", fake.all_names() == [],
          fake.all_names())
finally:
    fake.close()

run = subprocess.run([sys.executable, str(ROOT / 'tscmanager.py'),
                      '--probe', '127.0.0.1:9', '--probe-wait', '0.2'],
                     capture_output=True, text=True, timeout=30)
check("a printer that is not there: a message and exit status 1",
      run.returncode == 1 and 'Probe failed' in run.stderr, run.stderr)

finish()
