#!/bin/bash

date=$(date -u +"%Y-%m-%d %H:%M:%S")

(sleep 1;echo -e 'root\nZte521';sleep 1;echo "date -u -s '$date'";sleep 1;exit)| telnet 192.168.1.1

exit 0