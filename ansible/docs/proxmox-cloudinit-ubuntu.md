# Proxmox Ubuntu 22.04 Cloud Init VM

This workflow creates an Ubuntu 22.04 VM on the Proxmox host `minsky`
using the official Jammy cloud image, cloud-init, DHCP, and DNS server
`10.0.0.1`.

## Starting Point

The Proxmox host OS is installed, reachable by Ansible, and the host is
already present in `inventory.yml` as `minsky`.

```sh
ansible all -m ping -l minsky
ansible minsky -m setup -l minsky
```

The second command runs Ansible's built-in `setup` module against
`minsky` and collects system facts. In this specific example, `minsky` is
specified twice: once as the inventory host pattern, and once as the
limit. These are effectively equivalent:

```sh
ansible minsky -m setup
ansible minsky -m setup -l minsky
```

Useful fact-gathering examples:

```sh
ansible minsky -m setup -a 'filter=ansible_default_ipv4*'
ansible minsky -m setup -a 'filter=ansible_hostname'
ansible minsky -m setup --tree ./facts
```

## Run The Reusable Workflow

From the `atlas` repository root:

```sh
ansible-playbook ansible/playbooks/proxmox-create-cloudinit-vm.yml -e @ansible/vars/minsky-ubuntu2204.yml -l minsky
```

Create the `agent` Ubuntu 22.04 guest on `minsky`:

```sh
ansible-playbook ansible/playbooks/proxmox-create-cloudinit-vm.yml -e @ansible/vars/minsky-agent-ubuntu2204.yml -l minsky
```

The `agent` vars omit `vmid`, so the role derives a deterministic VMID
from `vm_name`. If the derived ID already exists and belongs to a
different VM, the role asks Proxmox for the next available ID with:

```sh
pvesh get /cluster/nextid
```

Override values inline:

```sh
ansible-playbook ansible/playbooks/proxmox-create-cloudinit-vm.yml -e @ansible/vars/minsky-ubuntu2204.yml -e vmid=2210 -e vm_name=test-ubuntu -l minsky
```

The hash-derived VMID defaults are:

```yaml
vmid: ""
vmid_base: 10000
vmid_range: 90000
vmid_hash_prefix_length: 8
```

Set `vmid` explicitly only when you need a specific Proxmox ID.

Destroy and recreate the VM:

```sh
ansible-playbook ansible/playbooks/proxmox-create-cloudinit-vm.yml -e @ansible/vars/minsky-ubuntu2204.yml -e destroy_existing_vm=true -l minsky
```

## Verify

```sh
ansible minsky -m command -a "qm list"
```

Use the VMID shown by `qm list` for detailed checks:

```sh
ansible minsky -m command -a "qm status VMID"
ansible minsky -m command -a "qm config VMID"
```

Check the DHCP lease from the router or DNS server at `10.0.0.1`, then
SSH to the VM:

```sh
ssh -i ~/.ssh/id_rsa_control control@VM_DHCP_ADDRESS
```

## Cloud Init User

`ci_user` maps to Proxmox's `ciuser` setting. It tells cloud-init which
operating system user account to create or configure inside the guest VM
during first boot.

```sh
qm set 2204 -ciuser control
qm set 2204 -cipassword MyPassword
```

This workflow uses a dedicated automation account and installs the
control public key from the Ansible control machine:

```yaml
ci_user: control
ci_ssh_public_key_file: "{{ lookup('env', 'HOME') }}/.ssh/id_rsa_control.pub"
ci_sudo: "ALL=(ALL) NOPASSWD:ALL"
ci_groups: sudo
```

The role writes a Proxmox cloud-init user-data snippet to
`/var/lib/vz/snippets` and attaches it with `cicustom`, which makes the
`control` user's sudo access explicit instead of relying on image
defaults.
