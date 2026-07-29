## OCI Enterprise AI Chain

Installation using terraform

### Parameters:

- Prefix added before each resource name)
- Compartment: compartment_ocid
- public_ip_filter
    IP Range that can access port like 80/443 on the internet. Typically:
    - All internet - 0.0.0.0/0
    - or <your_laptop_ip>/32. Get your Laptop IP, by example, using https://whatismyipaddress.com
- your_public_ssh_key
    - Your ssh public key (associated with your private key stored in your laptop) that will be added in .ssh/authorized host in the bastion.
    - Goal: clone the git repository on your laptop for Vibe Coding

- project_ocid="__TO_FILL__"
    - OCI GenAI Project OCID

- genai_endpoint_ocid
    - DAC

- openid="true"
    - Uncomment to enable login in LangGraph application using OpenID via API Gateway and Confidential Application 
    - Needs OCI Identity Domain rights.

- LangFuse
    - langfuse_public_key="pk-lf-change-it"
    - langfuse_secret_key="sk-lf-change-it"
    - langfuse_base_url="http://langfuse-compute.##PREFIX##web.##PREFIX##vcn.oraclevcn.com:3000"

...


### Usage

### Commands
- starter.sh             : Show the menu
- starter.sh help        : Show the list of commands
- starter.sh build       : Build the whole program: Run Terraform, Configure the DB, Build the App, Build the UI
- starter.sh destroy     : Destroy the objects created by Terraform
- starter.sh env         : Set the env variables in BASH Shell
- starter.sh ssh bastion : SSH to the Bastion
- ...
                    
### Directories
- src           : Sources files
    - app       : Source of the Application
        - db    : Database SQL files
        - rest  : Backend - REST Application
        - ui    : Frontend - User Interface
    - terraform : Terraform scripts
    - compute   : Contains the deployment files to Compute

Help (Tutorial + How to customize): https://www.ocistarter.com/help

### Next Steps:
- Edit the file terraform.tfvars. Some variables need to be filled:
```
public_ip_filter="__TO_FILL__"
your_public_ssh_key="__TO_FILL__"
```

- Run:
  cd chat
  ./starter.sh
