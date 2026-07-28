#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR

. ../tf_env.sh

# Bootstrap an isolated local runtime on first use. This avoids relying on the
# Compute-only `myenv` and `port_wait` helpers used by start.sh.
VENV_DIR="${VENV_DIR:-$SCRIPT_DIR/.venv}"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR"
fi

if ! "$VENV_DIR/bin/python" -c 'import aiohttp, fastapi, langchain_oci' >/dev/null 2>&1; then
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/python" -m pip install -r requirements.txt
fi

# CONFIG uses the OCI config-file profile for both LangChain and the local
# OpenAI-compatible/vector-search clients. Deployment start.sh keeps its
# instance/resource-principal configuration.
export AUTH_TYPE="${AUTH_TYPE:-CONFIG_FROM_FILE}"
export OCI_CONFIG_FILE="${OCI_CONFIG_FILE:-$HOME/.oci/config}"
export OCI_CONFIG_PROFILE="${OCI_CONFIG_PROFILE:-DEFAULT}"
export REGION="${REGION:-$TF_VAR_region}"
export PROJECT_OCID="${PROJECT_OCID:-$TF_VAR_project_ocid}"
export COMPARTMENT_OCID="${COMPARTMENT_OCID:-$TF_VAR_compartment_ocid}"
export PORT="${PORT:-8080}"
export REST_AUTH_ENABLED="${REST_AUTH_ENABLED:-false}"

exec "$VENV_DIR/bin/python" -m uvicorn rest:app --host 127.0.0.1 --port "$PORT" | tee rest.log
