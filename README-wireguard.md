# Ansible playbook for remote Wireguard deployment

The purpose of this playbook, affectionately referred to as "VPNator", is to help with the remote installation, deployment, stoppage and removal of WireGuard on Debian based systems. Currently, only up-to-date Debian 10 is sure to be supported.

When run naively,
```bash
ansible-playbook vpNator-wireguard.yml
```
this playbook prompts you for an action. You can :

 1. : Install WireGuard's package (usually, to compile the associated kernel module), set up and configure  
 2. : Start WireGuard and FireQOS
 3. : Stop WireGuard and FireQOS
 4. : Remove WireGuard and the other tools.
 5. : Uninstall and install everything (do a complete round of purge, install and launch)

## Technical Details

This part of the document contains more explicit and detailed explanations of what our playbook does, why it is written that way, and how to navigate its code. It assumes that the reader is already familiar with the basics of YAML file structures and common Ansible modules. Feel free to read the Ansible modules documentation alongside this document if needed. Some useful actions available using simple Ansible options are brought to the attention of the reader.

### Technical generalities

The way VPNator is typically run at INSALan, a simple call to `ansible-playbook` is enough. However, if your remote user happens to need a sudo password, or the remote SSH connection requires a password (or keys you haven't loaded), then :
  - Remember to load any keys you need to before you start the playbook
  	```bash
 	ssh-add $PATH_TO_KEY/my_key
 	```
  - Launch Ansible with the `-K` or `--ask-pass` option. Ansible will prompt you for the password to use for the privilege ascension mechanism used (here, that is sudo).

#### Adding remote hosts

Our version of VPNator connects to any remote machine under the `vpn` inventory with the login `debian`, and no password. Remote hosts are listed in the inventory `/etc/ansible/hosts` in the following fashion :

```
[vpn]

vpn1 id=1
vpn2 id=3
ovh1 id=100 ansible_user=bidule
```

The subnet used within a tunnel is computed using that id. It must be an integer between `1` and `254`. The local host will take ip address 1 on that subnet on the interface corresponding with the VPN connection, and the VPN will take address 2.

Note that, using Ansible's terminology, `vpn1` and so on are host names (which should ideally be aliased to ip addresses/resolvable domain names) list under the same "inventory".

The `ansible_user` host variable is a documented ansible variable that indicates what user to log in as on that specific host. It is typically set to "debian", and when undefined that is the value taken.

#### Modifying specific variables

Various aspects of the playbook can be modified on a global level.
  - The port on which WireGuard should listen for incoming connections is modified around line 37 in the `port` variable
  - The address of the remote server on the tunnel is computed using their peer id in the pattern `10.8.id.1`. The local address on that tunnel is also computed around line 35. It is `10.8.id.2`.
  - The local WireGuard interface is called `tunid` where `id` is the host id, and that can be changed in the `localhost_wg_interface` interface.

All of these variables can be set either by modifying the playbook, or by providing extra arguments (which will override those set in the playbook) using the `-e` or `--extra-vars` option of `ansible-playbook`, followed by pairs of `key=val` strings. For example, you can change the `extra_args` variable to change the port WireGuard listens on 
```bash
ansible-playbook vpNator-wireguard.yml -e port=5010
```

Using additional external arguments is recommended for one-time uses. When long-term persistent modifications are needed, modify the playbook/host inventory files themselves.

#### Limiting playbook runs

It is also possible to limit the playbook's run to a particular machine among the group `vpn` (or any other you have chosen to use instead), using the `-l` option and providing individual hostnames or any pattern. Ansible will match individuals in the original pool of hosts and their data against that pattern, and only run the playbook for those successfully matched.

***BE CAREFUL : When limiting ansible to a set of hosts that does not contain localhost, the menu asking you which operation you want to execute will be bypassed. This can be fixed by adding 'localhost' in the list of restricted hosts, or by providing activity tags.***

### Structure of the Playbook

This Ansible playbook is designed such that actions requested by the user will always follow the logical order they should be executed in.

When run without tags, the playbook launches a local play that prompts the user for an action to take (i.e. what flags to set). This play sits almost at the top of the playbook in order to be executed first when needed.

Once appropriate flags are set, the playbook begins. In order, it can
  1. Bring remote and local WireGuard interfaces down, destroying all connections
  2. Stop FireQOS
  3. Uninstall and purge FireQOS
  4. Remove the forwarding networking rules
  5. Uninstalling WireGuard and purging its configuration
  6. Remove the interfaces we created for WireGuard, destroying their configuration, and removing the copies of the private keys we generated
  7. Install additional packages typically used in production to probe and operate on the VPS
  8. Generating and storing local and remote encryption keys on the hard drive 
  9. Installing the linux headers and DKMS modules for WireGuard, along with the utility called `wg`
  10. Creating and setting up network interfaces on both ends
  11. Set up addresses on both ends
  12. Let both ends know about each other
  13. Enable IP forwarding on the system
  14. Add IP table rules to masquerade outbound traffic
  15. Bring the WireGuard interfaces up on the VPS, and locally
  16. Start FireQOS

You may notice that operations 1-2 correspond to a typical "stop", operations 3-6 correspond to an uninstallation, 7-14 to an installation, and 15-16 to a start. This way, when the user requests one of these operations, Ansible simply examines the conditions between the groups of actions above and skips over those that do not correspond. When an operation like a "stop & purge" is requested, everything beyond operation 6 is skipped. This way, none of the typical operations needed to handle VPN deployment and maintenance requires more than a single run of the playbook.

In the next subsection, we go over the technical details of each of these actions the user can take and how they are realized.

### Available actions

#### Stopping

 - **What does it do?** To be quite explicit, this action brings the remote and local WireGuard networking interfaces on the VPS and local host, and disables FireQOS.

 - **How is it done?** After calling `ip link set X down`, the interfaces still exist, and their configuration remains, but all connections are suddenly killed.
 FireQOS has a command called `stop` that simply disables it.

 - **How do I know it worked?** On both the VPS and the local host, you should observe that the virtual network devices `tunX` (or whatever you're calling it) associated with your VPN are no longer 'Up'. You can check that with `ip -c a` or `ip link`. There is no specific way to detect whether FireQOS is stopped or not (since it's not a running process), but we have never observed any failure with `fireqos stop` unless FireQOS wasn't started in the first place.

#### Uninstallation

 - **What does it do?** This action removes the `wireguard` package, additional tools and any other file we may have transferred to run our VPN.

 - **How is it done?** Most of the file deletion operations are run using Ansible's `file` module. FireQOS' configuration file is the first to go.
 Then the IP rule we added in order to enable Native Address Translation (or NAT) is removed using `iptables -t nat -D ...` (since our rule is present in the `nat` table; the omitted part contains the exact copy of a rule explained in details in the Installation operation).
 Until recently, most of the tools typically used by people at INSALan were removed and purged alongside WireGuard's packet using the `apt` module. This has caused issues in testing since some of these are dependencies for other programs, and caused massive interference (especially since a purge of configuration and data was requested). Notably, `openssl` is listed in the `packages` variable, and is a dependency for many IM server daemons.

 - **How do I know it worked?** If this operation worked, `apt search wireguard` should show you that the package `wireguard` is no longer installed. You should see none of the nodes listed above in the file system. Running `sudo iptables-save` should not show you the iptable line used to enable NAT.

#### Installation

 - **What does it do?** This action installs our typically useful programs, then WireGuard. It copies some configuration files over to the VPS, for FireQOS. Some network rules are set as well.

 - **How is it done?** First and foremost the `apt` module is used to install all of the packages in the `packages` variable, after an update of the package list is done. This is typically very slow, especially if it is run for the first time on a VPS.

	***An important note on our call to the apt module*** : We pass the option `install_recommends` and set it to `false` since one of the recommended packages of `fireqos`, `firehol` (but not `firehol-common`), has a habit of ***locking us outside of the VPS***. We prevent this package from being installed, and especially run, by asking ansible not to install recommended packages alongside the ones we ask it to install. It also makes things run a little faster.

	The configuration file `template/fireqos_vpn.conf` is sent over to the server in `/etc/firehold/`. Note that the remote interface name is hardcoded in order to be compatible with the OpenVPN version of this playbook.

	***Building the kernel module***
	WireGuard works using a kernel module that is responsible for handling very specific types of network interfaces. One can create these interfaces with
	```sh
	ip link add wg0 type wireguard
	```
	And this what we do. But in order for this to work, the type `wireguard` must be known to the Linux kernel at run-time. A kernel module called `wireguard.ko` must be loaded. You can check whether that is the case using
	```sh
	lsmod | grep wireguard
	```
	Installing the `wireguard` apt package does not necessarily install said module. With versions of Debian that have a linux kernel above version `5.6.0`, the module is shipped along with your installation of the kernel. If that is not the case (and currently for Debian 10 stable without backports it isn't), the `wireguard` package depends on another one called `wireguard-dkms`. When it is unpacked, it compiles the source code for the `wireguard` kernel module, installs it and loads it. Note that `bc` is a required dependency, that is why it is listed among the needed tools.

	Since kernel module compilation requires a version of the linux kernel headers that matches the kernel currently running, it is your job when deploying WireGuard to know whether the headers corresponding to the currently running version can be installed. Our playbook does attempt to use `uname -r` to figure out the kernel version and install the appropriate headers. If you cannot, it will be impossible to run WireGuard without excruciating pain.


	***Network Forwarding Rules***

	 IP forwarding is enabled by the kernel after the value 1 is "cat-ed" into `/proc/sys/net/ipv4/ip_forward`. Only IPv4 forwarding is enabled, but this is not (yet) an issue.

	Finally, an IP table rule is added to the IP table `nat` in the `POSTROUTING` chain to enable masquerading (i.e. substitution of actual sender address in IP headers with the machine's IP and the opposite for inbound traffic) whenever a packet leaves through the external network interface (usually called `en*` or `eth*` in Debian).

 - **How do I know it worked?** Typically when everything here worked out, Ansible will not show any error, and you'll notice that every file mentioned above is at the right place. Running `iptables-save` will show the IP table rule line mentioned (at least once).

#### Launching

 - **What does it do?** The last action brings both WireGuard interfaces up and starts FireQOS on both the local and remote hosts.
 - **How is it done?** The following command brings the interface `wg69` up
    ```bash
    ip link set wg69 up
    ```
    This is done on both local and remote hosts, such that connections can be initiated using both interfaces.

   And finally FireQOS is started by simply using `fireqos start` on the remote host. Remember that FireQOS does not actually run a process, so `fireqos start` simply enables the tools we use for monitoring on remote systems.

 - **How do I know it worked?** The network interfaces `tunX` (or whatever you called it) should be 'UP' on both ends of the tunnel. You can check using `ip -c a` (or any command to display the list of network interfaces). You should be able to log onto the remote host by using the following command where `<address>` stands for the IPv4 address assigned to the `tunX` network interface of said remote host
	```bash
	ssh debian@<address>
	```
	If this works you have successfully logged onto the remote host through the VPN tunnel. Further testing is usually done by trying to access the global internet (typically websites such as your favorite search engine) in order to check that the VPN actually forwards network traffic.

### An explanation of the IP table rule

As described in the documentation of `iptables`, the `nat` table is consulted whenever a packet creates a new connection. When NAT is enabled at that stage, the remainder of the connection is done under the impression of the external peer (i.e. not our VPS) that it is legitimately talking to the VPS itself, when, in actuality, some packages are emitted by players in the LAN, rise into our VPN tunnels, exit at the VPS, undergo masquerade, and then leave.

Specifically, the `POSTROUTING` chain is called just as packets are about to leave. This makes sense, since we only wish to masquerade packets that WireGuard, running on the VPS, emits to the outside world, stemming from data circulating in the tunnels. Moreover, those packets should only be masqueraded whenever they leave the VPS and try and contact the outside world. Since *we are always supposed to make first contact in any connection that transits through WireGuard*, it makes sense to only masquerade those packets that will leave for the `en+` interface.

All of these requirements explain the following line of IP table rule :
```bash
iptables -t nat -A POSTROUTING -o en+ -j MASQUERADE
```

What is not explained here is simple `iptables` syntax : the `-t` parameter gives the table (here it's `nat`), the `-A` parameter indicates that we should append to the chain provided (here `POSTROUTING`) and the rest is the rule. Whenever the requirements (that a packet establishing a connection be about to leave for the outside world, the action listed after `-j` is

## Common troubleshooting

The following is a short list of typical errors that are encountered while using VPNator.
 - Skipped errors during stop operation : VPNator tries to `ip link set down` on the remote host when they don't exist. If WireGuard is not running (either because you haven't started it yet or because you manually killed it, or maybe it crashed but we've never seen that yet), this will fail, and Ansible will catch that failure. To prevent the playbook from failing when that happens, this error is ignored. The same thing is done for `fireqos stop`.
 - No traffic goes through one or more of the VPNs but the tunnels work : this should not happen any more, but do check that both the IP table rule and IP forwarding are set as expected.
