#!/bin/bash

for server in `seq 6`; do
	scp fireqos_vpn.conf vpn$server:/etc/firehol/fireqos.conf
	ssh vpn$server fireqos start
done
