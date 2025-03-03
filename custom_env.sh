#!/bin/bash

{
    echo "LAN_IP=192.168.30.13"
    echo "GATEWAY_IP=192.168.30.11"
} >> modules/lan/.env

{
    echo "ADH_PASSWD=$2a$10$DDp.ZewovqT8ODxry7bC2ulduZ0bNlQAHkO1YCxe/AsTqq1NBS.b2"
} >> modules/adguardhome/.env

echo "CLASH_CONFIG_URL=https://gist.github.com/EkkoG/20a52db0169c4a4769689521b1c5500e/raw/cf61a9397d0bdbd5b6bbad8fbb388ec851116470/clash_example.yaml" >> modules/openclash/.env