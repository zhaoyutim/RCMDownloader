#!/bin/bash
cd "$(dirname "$0")"
python eodms_cli.py -i "$1"
read -p "Press any key to continue..."
