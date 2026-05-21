#!/usr/bin/env bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR
. $HOME/compute/tf_env.sh

# OCI Enterprise AI: set to your tenancy's region
export OCI_REGION=$TF_VAR_region
export OCI_COMPARTMENT_ID=$TF_VAR_compartment_ocid
export OCI_GENAI_PROJECT_ID=$TF_VAR_genai_project_ocid

# Container deployments (RESOURCE_PRINCIPAL or INSTANCE_PRINCIPAL instead of config file)
export USE_PRINCIPAL="INSTANCE_PRINCIPAL"

# export IDCS_DOMAIN_URL=https://idcs-xxxx.identity.oraclecloud.com
# export IDCS_CLIENT_ID=...
# export IDCS_CLIENT_SECRET=...
# export SESSION_SECRET=<random-long-string>

# export LANGFUSE_SECRET_KEY=sk-lf-...
# export LANGFUSE_PUBLIC_KEY=pk-lf-...
# export LANGFUSE_BASE_URL=https://cloud.langfuse.com
# export LOG_LEVEL=info

cd files
export PORT=8080
npm run dev > ../chat.log 2>&1 
