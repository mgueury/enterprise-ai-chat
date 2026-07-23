#!/usr/bin/env bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR

. $HOME/compute/shared_compute.sh
install_nodejs

cd files
npm install

sudo firewall-cmd --zone=public --add-port=8082/tcp --permanent