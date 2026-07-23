#!/usr/bin/env bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR/..

. starter.sh env -silent

get_ui_url

echo 
echo "Build done"

# Do not show the Done URLs if after_build.sh exists 
if [ "$UI_URL" != "" ]; then
    echo "URLs" > $FILE_DONE
    append_done "- User Interface: $UI_URL/"     
    if [ "$UI_HTTP" != "" ]; then
        append_done "- HTTP : $UI_HTTP/"
    fi
    if [ "$TF_VAR_ui_type" == "langgraph" ]; then
        append_done "- REST: $UI_URL/app/threads"
    else
        append_done "- REST: $UI_URL/app/dept"
        append_done "- REST: $UI_URL/app/info"    
    fi
    append_done "-----------------------------------------------------------------------"
    append_done "Vibe Coding (Build done in Bastion):"
    append_done
    if [ "$TF_VAR_your_public_ssh_key" != "" ]; then
        append_done "1. Check that you can login from your laptop to the bastion using the private key associated with your_public_ssh_key in terraform.tfvars"
        append_done "> ssh opc@$BASTION_IP"
    else
        append_done "1. Be sure that you can login from your laptop to the bastion by adding your SSH key to the bastion"
        append_done "   - or add the private key created in target/ssh_key_starter in your laptop"
        append_done "   - or login to the bastion (./starter.sh ssh bastion and add your own public key in $HOME/.ssh/authorized_keys)"
    fi
    append_done "2. Clone the git repo of the starter app in your laptop"
    append_done "> git clone opc@$BASTION_IP:~/app.git app"
    append_done "> cd app"
    append_done "3. Do some changes with your favorite editor."
    append_done "4. Check what git_push.sh does and run it."
    append_done "> ./git_push.sh"
    append_done "The build will start automatically in the bastion and redeploy the app."
    append_done
    append_done "5. If you want to see the log. ssh opc@$BASTION_IP"
    append_done "> cat compute/rebuild.log"
    append_done "> cd app/xxxx" 
    append_done "> cat xxxx.log" 

elif [ ! -f $FILE_DONE ]; then
    echo "-" > $FILE_DONE  
fi
cat $FILE_DONE  