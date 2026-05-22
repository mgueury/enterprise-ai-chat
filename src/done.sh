#!/usr/bin/env bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR/..

. starter.sh env -silent

get_ui_url

echo 
echo "Build done"
echo 

# Do not show the Done URLs if after_build.sh exists 
if [ "$UI_URL" != "" ]; then
    echo "URL:" > $FILE_DONE
    append_done "- OCI Enterprise AI - chat: https://$APIGW_HOSTNAME/" 
elif [ ! -f $FILE_DONE ]; then
    echo "-" > $FILE_DONE  
fi
cat $FILE_DONE  