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

elif [ ! -f $FILE_DONE ]; then
    echo "-" > $FILE_DONE  
fi
cat $FILE_DONE  