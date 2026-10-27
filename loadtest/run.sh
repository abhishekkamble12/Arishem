#!/usr/bin/env bash
# Run the query load test at several concurrency levels and save Locust's CSVs.
#
#   bash loadtest/run.sh <label> <users> [<users> ...]
#   bash loadtest/run.sh baseline 1 2 4 8 16 32
#
# Start (or restart) the stack with the server settings under test first; this
# script never changes it. Each level runs for RUN_SECONDS (default 60). Results
# land in loadtest/results/<label>_u<users>_stats.csv, next to <label>_server.txt,
# which records the gunicorn command the API was actually running.
set -euo pipefail
cd "$(dirname "$0")"
label=$1; shift
seconds=${RUN_SECONDS:-60}
mkdir -p results
compose=(docker compose -f docker-compose.loadtest.yml)
api_cmd() { docker inspect "$("${compose[@]}" ps -q api)" --format '{{join .Config.Cmd " "}}'; }
before=$(api_cmd)
echo "$before" > "results/${label}_server.txt"
echo "API: $before"
for users in "$@"; do
  echo "== $label: $users users for ${seconds}s"
  # --no-deps: without it, `run` re-creates the API whenever the compose file or
  # its variables differ from the running container, silently swapping the
  # settings under test for the defaults. That happened once; see README.md.
  # MSYS_NO_PATHCONV stops Git Bash on Windows rewriting the /mnt paths.
  MSYS_NO_PATHCONV=1 "${compose[@]}" run --rm --no-deps locust \
    -f /mnt/locust/locustfile.py --host http://api:8000 --headless --only-summary \
    -u "$users" -r "$users" -t "${seconds}s" --csv "/mnt/locust/results/${label}_u${users}"
done
if [ "$(api_cmd)" != "$before" ]; then
  echo "The API changed during the run; these results are not one configuration." >&2
  exit 1
fi
python summarize.py "$label"
