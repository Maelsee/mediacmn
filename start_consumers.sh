#!/usr/bin/env bash

set -euo pipefail

# 用法:
#   ./start_consumers.sh dev
#   ./start_consumers.sh prod

MODE=${1:-dev}

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

QUEUE_LIST="scan,metadata,persist,delete,localize"

export PYTHONPATH="$BASE_DIR/media-server"

if [ "$MODE" = "dev" ]; then
  export DRAMATIQ_WORKER_PROCESSES=1
  export DRAMATIQ_THREADS=8
  export DRAMATIQ_PREFETCH=8
elif [ "$MODE" = "prod" ]; then
  export DRAMATIQ_WORKER_PROCESSES=4
  export DRAMATIQ_THREADS=16
  export DRAMATIQ_PREFETCH=32
else
  echo "Unknown mode: $MODE"
  exit 1
fi

echo "Starting consumers in $MODE mode for queues: $QUEUE_LIST"

# 确保使用虚拟环境的 python
VENV_PYTHON="$BASE_DIR/media-server/venv/bin/python3"

# exec source "$BASE_DIR/media-server/venv/bin/activate"

exec $VENV_PYTHON -m dramatiq services.task.consumers -Q scan -Q metadata -Q persist -Q delete -Q localize
