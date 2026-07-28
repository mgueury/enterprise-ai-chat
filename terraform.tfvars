# -- Variables ---------------------------------------------

# Prefix to all resources created by terraform
prefix="chat"

# Compartment OCID
compartment_ocid="__TO_FILL__"

# IP Range that can access port like 80/443 on the internet. Typically:
#   - All internet - 0.0.0.0/0
#   - or <your_laptop_ip>/32. Get your Laptop IP, by example, using https://whatismyipaddress.com
public_ip_filter="__TO_FILL__"

# Your ssh public key (associated with your private key stored in your laptop) that will be added in .ssh/authorized host in the bastion.
#   Goal: clone the git repository on your laptop for Vibe Coding
your_public_ssh_key="__TO_FILL__"

# Use in OpenAI responses API (+tools)
project_ocid="__TO_FILL__"

# DAC
# genai_endpoint_ocid="ocid1.generativeaiendpoint.oc1.uk-london-1.amaaaaaa2xxap7ya4nxzxjr227ju2p5mg3yvyyqufj272hm77z5a3na46t6q"

# Uncomment to enable login in LangGraph application using OpenID via API Gateway and Confidential Application 
# Needs OCI Identity Domain rights.
# openid="true"

# LangFuse
# langfuse_public_key="pk-lf-change-it"
# langfuse_secret_key="sk-lf-change-it"
# langfuse_base_url="http://langfuse-compute.##PREFIX##web.##PREFIX##vcn.oraclevcn.com:3000"