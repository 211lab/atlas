# Replace the `agent` guest with `hermes` on Minsky

Status: draft
Owner: —
Date: 2026-10-08

## Goal

Retire the `agent` VM (Proxmox VMID 87765) on the standalone Proxmox host
`minsky` (`10.0.0.106`) and provision a replacement Ubuntu 22.04 cloud-init
guest named `hermes` using the existing reusable workflow, matching the live
`agent` sizing. Update the declared references (`inventory.yml`, Pi-hole DNS)
from `agent` to `hermes`.

## User-visible behavior

- `qm list` on Minsky no longer shows a VM named `agent`.
- `qm list` on Minsky shows a running VM named `hermes` with 4 cores,
  12288 MB memory and a 64 GiB disk, DHCP on `vmbr0`, cloud-init user `control`,
  and the QEMU guest agent enabled.
- `inventory.yml` lists the service host as `hermes` (not `agent`).
- The Pi-hole DNS source declares `hermes.atlas.lan` (not `agent.atlas.lan`).

## Non-goals

- No change to the k3s cluster, its nodes, or any Kubernetes workload.
- No change to any host other than Minsky.
- No commit or push unless separately requested.

## Follow-up (completed)

- Refreshed the snapshot docs to `hermes` and removed the snapshot/verification
  date stamps: `docs/infrastructure-review.md`, `docs/c4-architecture.md`,
  `docs/architecture/placement.md`, `docs/kubernetes-control-plane.md`,
  `docs/atlas-dns.md`, and the `atlas-cluster` skill heading. Intrinsic factual
  dates (certificate expiry) were retained.
- Removed the stale `ansible/vars/minsky-agent-ubuntu2204.yml`.

## Acceptance criteria

- Given Minsky, when the change is applied, then `qm status 87765` fails and no
  VM named `agent` appears in `qm list`.
- Given the playbook run, then a VM named `hermes` exists and is running with
  `cores=4`, `memory=12288`, `scsi0` size `64G`, `onboot=1`, `ipconfig0=ip=dhcp`,
  `ciuser=control`, and `agent: enabled=1`.
- Given `inventory.yml`, then the `services` group contains host `hermes` and no
  host `agent`.
- Given `ansible/playbooks/roles/pihole/defaults/main.yml`, then the non-k8s
  service record is `hermes.atlas.lan` and no `agent.atlas.lan` remains.
- Given `ansible/vars/minsky-hermes-ubuntu2204.yml`, then it exists with
  `vm_name: hermes`, `vm_cores: 4`, `vm_memory: 12288`, `vm_disk_size: 64G`.

## Constraints

- Use the existing `proxmox-create-cloudinit-vm.yml` playbook and
  `proxmox_cloudinit_vm` role; do not hand-roll `qm` commands for creation.
- Deletion is destructive and irreversible; the `agent` guest contents are
  unknown (SSH to `10.0.10.155` timed out in the 2026-10-07 review).
- The deterministic VMID for `hermes` is 94266 (sha1-derived), distinct from
  `agent` 87765.

## Assumptions

- ASSUMPTION: "the same way" means the same workflow and the live `agent`
  sizing (4 vCPU / 12 GiB / 64 GiB), not the stale committed vars file
  (2 vCPU / 4 GiB / 32 GiB). Confirmed by the operator.
- ASSUMPTION: `hermes` uses a static service address `10.0.10.1/8` (gateway
  `10.0.0.1`), chosen by the operator after DHCP initially leased `10.0.10.138`.
  The Proxmox `ipconfig0` and the guest netplan both encode the static address.
- ASSUMPTION: updating the Pi-hole DNS *source* is sufficient; applying it to
  the live Pi-hole requires a separate `pihole.yaml` playbook run.

## Open questions

- None outstanding. The snapshot refresh and the commit/push were requested and
  performed as follow-ups.
