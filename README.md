## OCI-Starter
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
db_password="__TO_FILL__"
```

- Run:
  cd starter
  ./starter.sh
