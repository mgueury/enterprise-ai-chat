#!/usr/bin/env bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR
. $HOME/compute/tf_env.sh

# OCI Enterprise AI: set to your tenancy's region
export OCI_REGION=$TF_VAR_region
export OCI_COMPARTMENT_ID=$TF_VAR_compartment_ocid
export OCI_GENAI_PROJECT_ID=$TF_VAR_project_ocid

export NEXT_PUBLIC_GENAI_API_URL="https://${APIGW_HOSTNAME}/api"

# Container deployments (RESOURCE_PRINCIPAL or INSTANCE_PRINCIPAL instead of config file)
export USE_INSTANCE_PRINCIPAL=true

if [ "$TF_VAR_openid_client_id" != "" ]; then
    export IDCS_DOMAIN_URL=$IDCS_URL
    export IDCS_CLIENT_ID=$TF_VAR_openid_client_id
    export IDCS_CLIENT_SECRET=$TF_VAR_openid_client_secret
    export SESSION_SECRET='abcdefgh1234567890'
fi    

export RESPONSES_BACKEND="${RESPONSES_BACKEND:-rest}"
export REST_RESPONSES_URL="${REST_RESPONSES_URL:-http://127.0.0.1:8080/responses}"
export REST_RESPONSES_AUTHORIZATION="${REST_RESPONSES_AUTHORIZATION:-User local-dev}"

# export LANGFUSE_SECRET_KEY=sk-lf-...
# export LANGFUSE_PUBLIC_KEY=pk-lf-...
# export LANGFUSE_BASE_URL=https://cloud.langfuse.com
# export LOG_LEVEL=info

cd files
export PORT=3000
npm run dev > ../chat.log 2>&1 
