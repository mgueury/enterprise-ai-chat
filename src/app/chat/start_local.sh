#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR
. ../tf_env.sh

export OCI_REGION=$TF_VAR_region
export OCI_COMPARTMENT_ID=$TF_VAR_compartment_ocid
export OCI_GENAI_PROJECT_ID=$TF_VAR_project_ocid

# Use the local REST service by default. Override RESPONSES_BACKEND=oci to
# bypass it, or override any value below for a separately deployed REST app.
export RESPONSES_BACKEND="${RESPONSES_BACKEND:-rest}"
export REST_RESPONSES_URL="${REST_RESPONSES_URL:-http://127.0.0.1:8080/responses}"
# The REST service's `User` scheme is its existing local-development mode.
# Production deployments should set this to an appropriate Bearer credential.
export REST_RESPONSES_AUTHORIZATION="${REST_RESPONSES_AUTHORIZATION:-User local-dev}"

cd files
export PORT="${PORT:-3000}"
exec npm run dev | tee ../chat.log
