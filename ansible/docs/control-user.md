# Control User Bootstrap

Atlas hosts are managed through a dedicated `control` account.

## Local SSH Key

The bootstrap role creates the local keypair if it is missing:

```sh
~/.ssh/id_rsa_control
~/.ssh/id_rsa_control.pub
```

The local SSH config should contain Atlas host entries that use:

```sshconfig
User control
IdentityFile ~/.ssh/id_rsa_control
IdentitiesOnly yes
BatchMode yes
```

`BatchMode yes` makes SSH fail instead of prompting for a password when
the key is not accepted.

## Bootstrap Hosts

The first bootstrap run needs an account that can become root. On fresh
Proxmox nodes, use root:

```sh
ANSIBLE_SSH_ARGS="-C -o ControlMaster=auto -o ControlPersist=60s -o BatchMode=no" \
ansible-playbook ansible/playbooks/bootstrap-control.yaml -u root -k
```

For only the cluster hosts plus `minsky`:

```sh
ANSIBLE_SSH_ARGS="-C -o ControlMaster=auto -o ControlPersist=60s -o BatchMode=no" \
ansible-playbook ansible/playbooks/bootstrap-control.yaml -u root -k -l 'atlas,minsky'
```

## What The Role Configures

The `control-user` role:

- installs `sudo`
- creates the `control` user
- locks the `control` password
- adds `control` to the `sudo` group
- writes `/etc/sudoers.d/control` with `NOPASSWD:ALL`
- installs `~/.ssh/id_rsa_control.pub` as the exclusive authorized key
- disables SSH password authentication for `control`
- reloads SSH when the user-specific SSHD config changes

## Normal Ansible Use

After bootstrap, `ansible.cfg` uses:

```ini
remote_user = control
ask_pass = false
private_key_file = ~/.ssh/id_rsa_control
```

Verify SSH and passwordless sudo:

```sh
ansible all -m ping -o
ansible all -b -m command -a 'id -u' -o
```

The sudo check should return `0` for each host.
