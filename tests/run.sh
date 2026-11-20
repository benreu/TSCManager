#!/bin/bash
# Run every suite. Each is a plain script that exits non-zero on a failure.
# Qt suites go through the offscreen platform plugin; GTK ones need a
# display, so they run under xvfb-run (apt install xvfb), falling back to
# DISPLAY. TSCMANAGER_TEST_DISPLAY=real puts them on DISPLAY, to watch.
cd "$(dirname "$0")/.."
status=0

for suite in tests/test_transport.py tests/test_tspl.py tests/test_cli.py \
             tests/test_manager.py tests/test_qt.py; do
  [ -f "$suite" ] || continue
  echo "=== $suite ==="
  QT_QPA_PLATFORM=offscreen python3 -u "$suite" || status=1
done

for suite in tests/test_gtk.py tests/test_conformance.py; do
  [ -f "$suite" ] || continue
  echo "=== $suite ==="
  if [ "$TSCMANAGER_TEST_DISPLAY" != real ] && command -v xvfb-run >/dev/null; then
    xvfb-run -a -s "-screen 0 1920x1080x24" python3 -u "$suite" || status=1
  elif [ -n "$DISPLAY" ]; then
    python3 -u "$suite" || status=1
  else
    echo "SKIPPED: needs xvfb (apt install xvfb) or a display"
  fi
done

exit $status
