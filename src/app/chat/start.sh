#!/usr/bin/env bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR
. $HOME/compute/tf_env.sh

# OCI Enterprise AI: set to your tenancy's region
export OCI_REGION=$TF_VAR_region
export OCI_COMPARTMENT_ID=$TF_VAR_compartment_ocid
export OCI_GENAI_PROJECT_ID=$TF_VAR_genai_project_ocid

# Local dev (API-key auth via ~/.oci/config)
export OCI_CONFIG_FILE=~/.oci/config
export OCI_CONFIG_PROFILE=DEFAULT

# Container deployments (Resource Principal instead of config file)
# export USE_RESOURCE_PRINCIPAL=true

# export IDCS_DOMAIN_URL=https://idcs-xxxx.identity.oraclecloud.com
# export IDCS_CLIENT_ID=...
# export IDCS_CLIENT_SECRET=...
# export SESSION_SECRET=<random-long-string>

# export LANGFUSE_SECRET_KEY=sk-lf-...
# export LANGFUSE_PUBLIC_KEY=pk-lf-...
# export LANGFUSE_BASE_URL=https://cloud.langfuse.com
# export LOG_LEVEL=info

npm run dev > chat.log 2>&1 
