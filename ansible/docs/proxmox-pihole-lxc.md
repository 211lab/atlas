# Proxmox Pi-hole LXC

How the dedicated Pi-hole is provisioned as an unprivileged LXC container on the
`memex` Proxmox host, and how it is tuned to run comfortably in a small memory
cap. Design and rationale live in [Dedicated Pi-hole DNS](../docs/pihole-dns.md);
the operating runbook (provision → wire → verify) is
[Pi-hole DNS runbook](../docs/pihole-runbook.md).

## Container

| Item | Value |
| --- | --- |
| Proxmox host | `memex` (standalone, `10.0.0.105`) |
| Container ID | hash-derived from the name (base 10000, range 90000) |
| OS template | `debian-12-standard_12.12-1_amd64.tar.zst` |
| Type | unprivileged, `features=nesting=1,keyctl=1` |
| Resources | 1 vCPU, 256 MiB RAM, 256 MiB swap, 4 GiB rootfs on `local-lvm` |
| Network | `eth0` on `vmbr0`, `10.0.0.10/24`, gw `10.0.0.1` |
| Hostname | `pihole` (`pihole.atlas.lan`) |
| Boot | `onboot=1`, started after create |
| Access | `~/.ssh/id_rsa_control.pub` installed for `root` at create time |

An LXC `--memory` is a **cgroup cap, not a reservation**: the container only
consumes what Pi-hole actually touches, so a low cap costs the host nothing at
idle.

## Create it

```sh
ansible-playbook ansible/playbooks/proxmox-create-pihole-lxc.yml \
  -e @ansible/vars/memex-pihole-lxc.yml -l memex
```

The `proxmox_lxc` role is idempotent: it derives the VMID, checks whether the
container exists, downloads the template with `pveam` if missing, stages the
Ansible public key on the Proxmox host, runs `pct create`, and ensures the
container is running.

Then bootstrap the `control` user and install Pi-hole:

```sh
ansible-playbook ansible/playbooks/bootstrap-control.yaml -l dns -u root
ansible-playbook ansible/playbooks/pihole.yaml \
  -e pihole_webpassword="$PIHOLE_ADMIN_PASSWORD" \
  -e 'pihole_local_records=[{"ip":"10.0.0.10","names":["pihole.atlas.lan","dns.atlas.lan"]},{"ip":"10.0.0.1","names":["router.lan","gw.lan"]}]'
```

## Memory-lean profile

Baked into the `pihole` role and applied idempotently via `pihole-FTL --config`:

| Setting | Value | Effect |
| --- | --- | --- |
| `dns.cache.size` | 2000 | smaller DNS cache |
| `database.maxDBdays` | 7 | short query-history retention |
| `database.DBinterval` | 300 | fewer DB writes |
| `dns.queryLogging` | false | no per-query logging |
| `misc.privacylevel` | 2 | aggregate client detail |
| `webserver.threads` | 10 | fewer web threads |

Override any of them per run with `-e pihole_ftl_settings=<list>`. The dominant
memory consumer is the gravity/blocklist domain set — keep the blocklists small
for the lowest footprint.

## DNS records

The role also configures what Pi-hole answers (see
[DNS in the Atlas lab](../docs/atlas-dns.md)):

- **Wildcard** — `address=/atlas.lan/<ip>` dnsmasq lines
  (`pihole_dnsmasq_lines` / `pihole_wildcard_targets`) send any unregistered
  `*.atlas.lan` name to the Traefik ingress nodes `10.0.0.110-113`.
- **Static records** — `pihole_local_records` writes literal `dns.hosts` entries
  for the Pi-hole itself, the router, the Proxmox nodes (`10.0.0.101-106`), the
  API VIP (`10.0.0.108`), and the non-k8s services (`10.0.10.24/26/155`). They
  are **merged** into `dns.hosts`, never replacing ExternalDNS-owned entries.

Adjust the container cap later without recreating:

```sh
ssh memex sudo pct set <vmid> --memory 256 --swap 256
```

## Verify

```sh
ssh memex sudo pct status <vmid>
ssh memex sudo pct exec <vmid> -- free -m
dig +short @10.0.0.10 pihole.atlas.lan
dig +short @10.0.0.10 github.com
```

## Rollback

```sh
ssh memex sudo pct stop <vmid>
ssh memex sudo pct destroy <vmid>
```

Then follow the rollback section of the [Pi-hole DNS runbook](../docs/pihole-runbook.md)
to remove the GitHub/Gitea wiring and re-point the network.
