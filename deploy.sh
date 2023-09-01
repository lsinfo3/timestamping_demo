#!/bin/bash



# Deploy sensor webui to the target pc
scp -r -P 22001 ./sensors demo@172.16.38.101:
ssh -p 22001 demo@172.16.38.101 bash -c '"cd ./sensors/query-sensors/ && make"'
ssh -p 22001 demo@172.16.38.101 bash -c '"cd ./sensors/sensor-webui/; python -m venv venv; source venv/bin/activate && pip install nicegui pandas netmiko psutil"'

scp -r -P 22002 ./sensor-view demo@172.16.38.101:
ssh -p 22002 demo@172.16.38.101 bash -c '"cd ./sensor-view/; python -m venv venv; source venv/bin/activate && pip install nicegui pandas matplotlib"'

