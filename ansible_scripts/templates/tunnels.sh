#!/bin/bash

#file="nabooVPNovh4.ovpn"

openvpn \
        --config /root/reseau15/vpn/openvpn_files/$1 \
	--route-noexec &

