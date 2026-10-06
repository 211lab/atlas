# atlas

Configuration management and GitOps for the 211 Lab Proxmox VE + K3s cluster.

> Lab-wide background, naming, and other projects live in the
> [211 Lab organization profile](https://github.com/211lab).

## Resources

https://github.com/lae/ansible-role-proxmox/tree/develop

https://docs.ansible.com/ansible/latest/collections/community/proxmox/proxmox_cluster_module.html

https://github.com/sbarbett/pihole-ansible

## Current infrastructure

The deployed Kubernetes platform is documented in [Kubernetes control plane](docs/kubernetes-control-plane.md). That runbook is the source of truth for the HA K3s topology, API VIP, control-plane access, monitoring, storage status, and operational guardrails.

The self-hosted git forge (Gitea), build runner, and Argo CD delivery pipeline are documented in [GitOps platform](docs/gitops-platform.md). Helm values and Argo CD Applications live under `gitops/` and `helm/`.

The whole platform (compute, storage, networking, control, delivery) is mapped in [C4 architecture](docs/c4-architecture.md) with Context, Container, Component, and Deployment diagrams.

An opencode agent skill that onboards an application end to end (add the `atlas` git remote, build, tag, deploy) lives at [`.opencode/skills/atlas-deploy-app`](.opencode/skills/atlas-deploy-app/SKILL.md).

DNS — the Pi-hole resolver on the network (wildcard `*.atlas.lan` plus static
records for non-Kubernetes hosts) and ExternalDNS auto-registration of Ingress
hostnames — is documented in [DNS in the Atlas lab](docs/atlas-dns.md).

## Process

Start with each node fresh with the Proxmox ISO.

Set IP of nodes in the proxmox setup `10.0.0.10X`

Bootstrap the `control` user with root credentials first. This is the
one run that may ask for the root SSH password:

```sh
ANSIBLE_SSH_ARGS="-C -o ControlMaster=auto -o ControlPersist=60s -o BatchMode=no" \
ansible-playbook ansible/playbooks/bootstrap-control.yaml -u root -k
```

Default Ansible access uses `root` over SSH with password auth prompts.
Verify connectivity:

```sh
ansible all -m ping -o -k
```

Run the regular maintenance playbooks:

```sh
ansible-playbook ansible/playbooks/update_all_packages_latest.yaml
ansible-playbook ansible/playbooks/no_subscription.yaml
ansible-playbook ansible/playbooks/sync-atlas-dns.yaml
```

Used the UI to create a cluster and copied the join info to each node with UI

had to debug babbage it wasn't reporting stats

first standardized on host files then ran through restart of certs and daemons

```
pvecm updatecerts -f
systemctl restart pve-cluster
systemctl restart corosync
systemctl restart pvestatd pvedaemon pveproxy
systemctl status pvestatd
```

## Notes

### 2026-04-10

- For memex to be a critical host I needed to remove it from the cluster as a stand alone node. With this there isn't a wait for Quorem to auto-start the VMs hosted on there.

- Updated `control` user with passwordless login and using local ssh key `id_rsa_control`

## Secret scanning

Sensitive values – API keys, tokens, private keys, and Tailscale identities
(`tskey-*` auth keys, `*.ts.net` MagicDNS names, and CGNAT tailnet IPs) – are
kept out of the repository by a [gitleaks](https://github.com/gitleaks/gitleaks)
config (`.gitleaks.toml`) that runs in two places:

- **Locally, before every commit**, via the tracked hook in `.githooks/`. Enable
  it once per clone:

  ```sh
  git config core.hooksPath .githooks
  ```

- **In CI, over the full history**, on every push and pull request (see
  `.github/workflows/gitleaks.yml`).

To scan manually:

```sh
gitleaks git --config .gitleaks.toml --redact            # whole history
gitleaks git --staged --config .gitleaks.toml --redact   # staged changes only
```

Encrypted `SealedSecret` ciphertext under `gitops/sealed/` is allowlisted; the
sealing private key is never committed. Internal `10.0.0.0/8` addresses and
`*.atlas.lan` names are intentionally public; tailnet identities are not.

## Docs

- [Kubernetes control plane](docs/kubernetes-control-plane.md) — deployed topology, kubeconfig access, monitoring, storage status, and recovery procedures
- [C4 architecture](docs/c4-architecture.md) — Context, Container, Component and Deployment diagrams for compute, storage, networking, control, and delivery
- [Dedicated Pi-hole DNS](docs/pihole-dns.md) — Ansible provisioning of a dedicated Pi-hole plus automatic Ingress-to-DNS registration (ExternalDNS / dnsweaver)
- [DNS in the Atlas lab](docs/atlas-dns.md) — the Pi-hole resolver on the network (wildcard + static records) and ExternalDNS auto-discovery of `atlas.lan` hostnames
- [Proxmox Pi-hole LXC](ansible/docs/proxmox-pihole-lxc.md) — create and tune the Pi-hole container on `memex`
- [Pi-hole DNS runbook](docs/pihole-runbook.md) — step-by-step: provision, seal the API password, wire the cluster, deploy ExternalDNS, verify, roll back
- [GitOps platform](docs/gitops-platform.md) — Gitea forge, container registry, Actions CI, Argo CD app-of-apps, image promotion, secrets, and storage
- [Home Assistant on Atlas](docs/home-assistant.md) — LAN-only K3s chart and GitOps setup, rollout/live verification, safe rollback, and operational limits
- [Sealing secrets](docs/sealing-secrets.md) — cluster-admin runbook: seal and re-seal SealedSecrets, scopes, consuming them from charts, sealing-key backup/rotation, troubleshooting
- [Control user bootstrap](ansible/docs/control-user.md)
- [Proxmox Ubuntu 22.04 cloud-init VMs](ansible/docs/proxmox-cloudinit-ubuntu.md)
- [SSH config from inventory](ansible/docs/ssh-config-from-inventory.md)
