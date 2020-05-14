# Ansible playbook for remote OpenVPN deployment

The purpose of this playbook, affectionately referred to as "VPNator", is to help with the remote installation, deployment, stoppage and removal of OpenVPN on Debian based systems. Currently, only Debian 9 is sure to be supported.

When run naively,
```bash
ansible-playbook vpNator-ovpn.yml
```
this playbook prompts you for an action. You can :

 1. : Install OpenVPN's package, copy the configuration files required over to the server, launch and mount the tunnels.
 2. : Remove OpenVPN and wipe the configuration clean.
 3. : Stop, remove, install, and restart OpenVPN (doing step 2 then 3).
 4. : Stop OpenVPN without uninstall it.
 5. : Start OpenVPN (requires prior installation)

## Technical Details

This part of the document contains more explicit and detailed explanations of what our playbook does, why it is written that way, and how to navigate its code. It assumes that the reader is already familiar with the basics of YAML file structures and common Ansible modules. Feel free to read the Ansible modules documentation alongside this document if needed. Some useful actions available using simple Ansible options are brought to the attention of the reader.

### Technical generalities

The way VPNator is typically run at INSALan, a simple call to `ansible-playbook`, passing any flags if needed, is enough. However, if your remote user happens to need a sudo password, or the remote SSH connection requires a password (or keys you haven't loaded), then :
  - Remember to load any keys you need to before you start the playbook
  	```bash
 	ssh-add $PATH_TO_KEY/my_key
 	```
  - Launch Ansible with the `-k` or `--ask-pass` option. Ansible will prompt you for the password to use for the privilege ascension mechanism used (here, that is sudo).

#### Adding remote hosts

Our version of VPNator connects to any remote machine under the `vpn` inventory with the login `debian`, and no password. Remote hosts are listed in the inventory `/etc/ansible/hosts` in the following fashion :

```
[vpn]

vpn1 subnet=$SUBNET1 fournisseur=vpn1 ansible_user=debian
vpn2 subnet=$SUBNET2 fournisseur=vpn2 ansible_user=debian
ovh1 subnet=$SUBNET3 fournisseur=ovh1 ansible_user=debian
```

where `$SUBNETX` is a subnet prefix in the likes of `10.8.2.0`. The local host will take ip address 1 on that subnet on the interface corresponding with the VPN connection, and the VPN will take address 2.

Note that, using Ansible's terminology, `vpn1` and so on are host names (which should ideally be aliased to ip addresses/resolvable domain names) list under the same "inventory".

The `fournisseur` key is later only referred to as `ovpnNumber` in the playbook or "VPN number" in this document.

The `ansible_user` host variable is a documented ansible variable that indicates what user to log in as on that specific host. It is typically set to "debian", and when undefined that is the value taken.

#### Modifying specific variables

Various aspects of the playbook can be modified on a global level.
  - The port on which OpenVPN should listen for incoming connections is modified around line 35 in the `port` variable
  - The protocol used by OpenVPN to transmit data is determined by the variable `protocol`
  - The variable `ovpnNumber` contains a unique identifier used to distinguish files from a specific VPS and its associated VPN
  - Default arguments passed to OpenVPN are defined by the variable `default_args`. Additional arguments should be written in `extra_args`.

All of these variables can be set either by modifying the playbook, or by providing extra arguments (which will override those set in the playbook) using the `-e` or `--extra-vars` option of `ansible-playbook`, followed by pairs of `key=val` strings. For example, you can change the `extra_args` variable to provide additional parameters to openvpn at launch by using
```bash
ansible-playbook vpNator-ovpn.yml -e extra_args='--local 127.0.0.1'
```

Using additional external arguments is recommended for one-time uses. When long-term persistent modifications are needed, modify the playbook/host inventory files themselves.

#### Limiting playbook runs

It is also possible to limit the playbook's run to a particular machine among the group `vpn` (or any other you have chosen to use instead), using the `-l` option and providing individual hostnames or any pattern. Ansible will match individuals in the original pool of hosts and their data against that pattern, and only run the playbook for those successfully matched.

***BE CAREFUL : When limiting ansible to a set of hosts that does not contain localhost, the menu asking you which operation you want to execute will be bypassed. This can be fixed by adding 'localhost' in the list of restricted hosts.***

### Structure of the Playbook

This Ansible playbook is designed such that actions requested by the user will always follow the logical order they should be executed in.

When run without flags, the playbook launches a local play that prompts the user for an action to take (i.e. what flags to set). This play sits almost at the top of the playbook in order to be executed first when needed.

Once appropriate flags are set, the playbook begins. In order, it can
  1. Kill OpenVPN on both remote and local hosts
  2. Stop FireQOS from running
  3. Uninstall tools and their configuration files (mostly FireQOS)
  4. Remove the iptable rules that masquerades outbound traffic
  5. Uninstalling OpenVPN and purging its configuration
  6. Remove more directories in which we store OpenVPN files (.ovpn) or the certificate generation script, or more configuration files
  7. Install additional packages typically used in production to probe and operate on the VPS
  8. Create a folder dedicated to storing VPN files
  9. Copy and run a certificate generation script
  10. Customize and copy OpenVPN configuration files
  11. Repatriate the customized OpenVPN files from the VPS
  12. Enable IP forwarding on the system
  13. Add IP table rules to masquerade outbound traffic
  14. Start OpenVPN on the VPS, and locally
  15. Start FireQOS

You may notice that operations 1-2 correspond to a typical "stop", operations 3-6 correspond to an uninstallation, 7-13 to an installation, and 14-15 to a start. This way, when the user requests one of these operations, Ansible simply examines the conditions between the groups of actions above and skips over those that do not correspond. When an operation like a "stop & purge" is requested, everything beyond operation 6 is skipped. This way, none of the typical operations needed to handle VPN deployment and maintenance requires more than a single run of the playbook.

In the next subsection, we go over the technical details of each of these actions the user can take and how they are realized.

### Available actions

#### Stopping

 - **What does it do?** To be quite explicit, this action kills any process called `openvpn` on the VPS and local host, and disables FireQOS.

 - **How is it done?** The killing of openvpn on remote hosts is simply done using `pkill openvpn`. It sens a `SIGTERM` signal to the openvpn process, which handles it as a shutdown request.

 Locally, since a single openvpn process deals with a single VPN connection, we restrict the killing process by matching a pattern against the full command line that launched openvpn, containing the name (and VPN number) of the configuration file for the specific connection we want to terminate.

 FireQOS has a command called `stop` that simply disables it.

 - **How do I know it worked?** On both the VPS and the local host, you should observe that the virtual network devices `tunX` associated with your VPN are no longer present. A `pgrep openvpn` on the VPS should yield nothing. There is no specific way to detect whether FireQOS is stopped or not (since it's not a running process), but we have never observed any failure with `fireqos stop`.

#### Uninstallation

 - **What does it do?** This action removes the `openvpn` package, configuration files, additional tools and any other file we may have transferred to run our VPN.

 - **How is it done?** Most of the file deletion operations are run using Ansible's `file` module. FireQOS' configuration file is the first to go.
 Then the IP rule we added in order to enable Native Address Translation (or NAT) is removed using `iptables -t nat -D ...` (since our rule is present in the `nat` table; the omitted part contains the exact copy of a rule explained in details in the Installation operation).
 Until recently, most of the tools typically used by people at INSALan were removed and purged alongside OpenVPN's packet using the `apt` module. This has caused issues in testing since some of these are dependencies for other programs, and caused massive interference (especially since a purge of configuration and data was requested). Notably, `openssl` is listed in the `packages` variable, and is a dependency for many IM server daemons. That being said, OpenVPN is still removed (but not purged), and later more files we sent over to run it are removed :
  - `/etc/openvpn` which contains all of the configuration OpenVPN uses
  - `/etc/sysctl.d/30-openvpn-forward.conf` which contains (we assume) system rules related to the forwarding of packets to and from openvpn.
  - `/home/vpn` where the certificate generation script is copied and run
  - `/home/client-{{ ovpnNumber }}` which is the OpenVPN configuration file for the specific VPN with number `ovpnNumber`

 - **How do I know it worked?** If this operation worked, `apt search openvpn` should show you that the package `openvpn` is not installed. You should see none of the nodes listed above in the file system. Running `sudo iptables-save` should not show you the iptable line used to enable NAT (although if it does it is not a problem).

#### Installation

 - **What does it do?** This action installs our typically useful programs, then OpenVPN. It copies a lot of configuration files over to the VPS, and a bash script to generate a certificate. Some network rules are set as well.

 - **How is it done?** First and foremost the `apt` module is used to install all of the packages in the `packages` variable, after an update of the package list is done. This is typically very slow, especially if it is run for the first time on a VPS.

 ***An important note on our call to the apt module*** : We pass the option `install_recommends` and set it to `false` since one of the recommended packages of `fireqos`, `firehol` (but not `firehol-common`), has a habit of ***locking us outside of the VPS***. We prevent this package from being installed, and especially run, by asking ansible not to install recommended packages alongside the ones we ask it to install. It also makes things run a little faster.

 A directory called `vpn` is created in the `home` directory using the `file` module. Then, a certificate generation script is customized and copied over to the VPS where it is run. More files are copied as well :
  - `server.conf.j2` is customized and copied to `/etc/openvpn` to act as the configuration file for the openvpn server
  - `client.conf.j2` is customized and copied to `/home/vpn` to act as the configuration file for a specific openvpn client
  - `dh.pem` is copied to `/etc/openvpn`. It is a typical Diffie-Hellman parameters file which seems to contain a certificate. For our purposes, we do not care about its strength or privacy.

 When we talk about "customizing", the reader should understand that specific fields delineated by `{{...}}` tags are detected in the files mentioned for the value stored in the variable `...` by Ansible. This way, for example, the `client.conf.j2` file can take the name `client-?.ovpn` where `?` is the VPN number corresponding to a specific instance.

 Once all of this is in place, the `.ovpn` client configuration file is modified once more so that the `tun` device name takes on a unique number at the end. That number corresponds to the place of a specific instance in the inventory of hosts listed in the `vpn` group. When this modification is done, that `.ovpn` file is copied back onto the local host into a folder called `openvpn_files` (which is created when it does not exist), located above the directory where Ansible is run.

 IP forwarding is enabled by the kernel after the value 1 is "cat-ed" into `/proc/sys/net/ipv4/ip_forward`. Only IPv4 forwarding is enabled, but this is not (yet) an issue.

 Finally, an IP table rule is added to the IP table `nat` in the `POSTROUTING` chain to enable masquerading (i.e. substitution of actual sender address in IP headers with the machine's IP and the opposite for inbound traffic) whenever a packet leaves through the external network interface (usually called `en*` in Debian).

 - **How do I know it worked?** Typically when everything here worked out, Ansible will not show any error, and you'll notice that every file mentioned above is at the right place. Running `iptables-save` will show the IP table rule line mentioned (at least once), and the `.ovpn` files will all be present in `openvpn_files` above the directory where you ran the playbook.

#### Launching

 - **What does it do?** The last action launches OpenVPN and FireQOS on both the local and remote hosts.
 - **How is it done?** On the remote host, OpenVPN is started by running the OpenVPN binary. The only argument provided is the path to the server configuration file uploaded during installation.
    ```bash
    /usr/sbin/openvpn --config /etc/openvpn/server.conf --daemon
    ```
    The `daemon` option ensures that `openvpn` forks and runs in the background, detached from the shell access granted to the Ansible 'command' module.

    Locally, OpenVPN is launched with a couple of different options. Among the default arguments are :
     - The path to the client configuration file `client-{{ ovpnNumber }}.ovpn` for obvious reasons
     - `route-noexec` is a flag that prevents OpenVPN from setting IP routes automatically on the client to redirect network traffic. Other scripts in the deployment procedure at INSALan handle IP rules and IP routes in exactly the way we want to.
     - `daemon` such that OpenVPN runs in the background.

   Supplementary arguments can be added by writing them in the `extra_args` variable in the beginning of the playbook.

   And finally FireQOS is started by simply using `fireqos start` on the remote host. Remember that FireQOS does not actually run a process, so `fireqos start` simply enables the tools we use for monitoring on remote systems.
 - **How do I know it worked?** A `pgrep` on both the remote and local hosts should yield at least one process ID on each machine (and hopefully only one). The network interfaces `tunX` should be visible on both ends of the tunnel using `ip -c a` (or any command to display the list of network interfaces). You should be able to log onto the remote host by using the following command where `<address>` stands for the IPv4 address assigned to the `tunX` network interface of said remote host
 ```bash
 ssh debian@<address>
 ```
 If this works you have successfully logged onto the remote host through the VPN tunnel. Further testing is usually done by trying to access the global internet (typically websites such as your favorite search engine) in order to check that the VPN actually forwards network traffic.

### An explanation of the IP table rule

As described in the documentation of `iptables`, the `nat` table is consulted whenever a packet creates a new connection. When NAT is enabled at that stage, the remainder of the connection is done under the impression of the external peer (i.e. not our VPS) that it is legitimately talking to the VPS itself, when, in actuality, some packages are emitted by players in the LAN, rise into our VPN tunnels, exit at the VPS, undergo masquerade, and then leave.

Specifically, the `POSTROUTING` chain is called just as packets are about to leave. This makes sense, since we only wish to masquerade packets that openvpn, running on the VPS, emits to the outside world, stemming from data circulating in the tunnels. Moreover, those packets should only be masqueraded whenever they leave the VPS and try and contact the outside world. Since *we are always supposed to make first contact in any connection that transits through OpenVPN*, it makes sense to only masquerade those packets that will leave for the `en+` interface.

All of these requirements explain the following line of IP table rule :
```bash
iptables -t nat -A POSTROUTING -o en+ -j MASQUERADE
```

What is not explained here is simple `iptables` syntax : the `-t` parameter gives the table (here it's `nat`), the `-A` parameter indicates that we should append to the chain provided (here `POSTROUTING`) and the rest is the rule. Whenever the requirements (that a packet establishing a connection be about to leave for the outside world, the action listed after `-j` is

### The certificate generation script

During the installation procedure, a shell script called `certgen.sh` is copied remotely, and later on executed. Its inner workings are detailed in this section.

This script is the last standing piece of shell script left from the original "Roadwarrior" OpenVPN script from which we created the ansible playbook. Both authors of the playbook decided to keep all of the operations related to certificate generation in that script, and to launch it remotely, in order to keep the playbook relatively clear.

The script starts by downloading and inflating an archive from OpenVPN's GitHub repository for the `easy-rsa` program. The contents of that archive are then copied over to `/etc/openvpn/easyrsa` where we operate.

Easy-RSA is used at first to generate what is called a 'PKI', or 'Public Key Infrastructure'. This is a system that wherein a Certificate Authority (CA) can receive certificate signing requests (CSRs) and generate certificates and certificate revocation lists (CRLs). These certificates are what interest us here.

A CA is built before the script generates two certificates (one for the server and one for the client), along with a CRL. Once the CA and both certificates have been built, they are copied into `/etc/openvpn` and their content is copied into the `.ovpn` client configuration file (between appropriate tags), so that the client has copies of these certificates too.

## Common troubleshooting

The following is a short list of typical errors that are encountered while using VPNator.
 - Skipped errors during stop operation : VPNator tries to `pkill openvpn` on the remote host. If OpenVPN is not running (either because you haven't started it yet or because you manually killed it, or maybe it crashed), this will fail, and Ansible will catch that failure. To prevent the playbook from failing when that happens, this error is ignored. The same thing is done for `fireqos stop`.
 - No traffic goes through one or more of the VPNs but the tunnels work : this should not happen any more, but do check that both the IP table rule and IP forwarding are set as expected.

## To-do list
 - Upgrade Easy-RSA in the certificate generation script to version 3.0.6.
