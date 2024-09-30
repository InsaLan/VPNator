#!/bin/python3
import subprocess
etc_hosts_filename = "/etc/hosts"
etc_ansible_hosts_filename = "/etc/ansible/hosts"
etc_firehol_vpn_list_filename = "/etc/firehol/vpn_list"
vpn_list = []
while True :
        a=input("Entrez l'adresse d'un vpn (touche A pour finir) \n")
        if a=="A":
                break
        vpn_list.append(a)

file = open(etc_hosts_filename, "r")
file_content = file.readlines()
file_right_content = []
for line in file_content:
        if "vpn" not in line :
                file_right_content.append(line)

file.close()

file = open(etc_hosts_filename, "w")
for line in file_right_content :
        file.write(line)
i = 1
for ip_vpn in vpn_list :
        file.write(ip_vpn + " vpn" + str(i) + "\n")
        i+=1
file.close()

file = open(etc_ansible_hosts_filename, "w")
file.write("[vpn] \n")
file.write("\n")
for i in range (len(vpn_list)) :
        file.write("vpn" + str(i+1) + " subnet=10.8." + str(i+1) + ".0 fournisseur=vpn" + str(i+1) + " ansible_user=debian \n")
file.close()

file = open(etc_firehol_vpn_list_filename, "w")
for i in range(len(vpn_list)) :
        file.write("vpn" + str(i+1) + "=" + vpn_list[i] +"\n")
file.close()

for i in range(len(vpn_list)) :
	s = "ssh-keygen -R vpn" + str(i+1)
	subprocess.run(args = s, shell = True)

