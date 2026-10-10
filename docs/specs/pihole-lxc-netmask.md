# Pi-hole LXC on the lab 10.0.0.0/8 subnet

## Goal

Put the Pi-hole LXC on the lab's `10.0.0.0/8` subnet so it treats every `10.x`
device as on-link, matching the rest of the lab. Today the container is pinned to
`10.0.0.10/24` while other lab guests use `/8` (e.g. `hermes` is
`10.0.10.1/8`, gateway `10.0.0.1`), so Pi-hole considers `10.0.10.x` clients
off-link and routes replies through the gateway instead of answering them
directly.

## User-visible behavior

- Pi-hole's `eth0` is `10.0.0.10/8` with gateway `10.0.0.1` on `vmbr0`.
- The repository (source of truth) declares the `/8` netmask, and the runbook
  documents the exact `pct set` + restart step to apply it to the existing
  container (the `proxmox_lxc` role only creates containers, so a vars change
  alone does not touch the live Pi-hole).
- Documentation shows the `/8` netmask.

## Non-goals

- Changing Pi-hole's IP (`10.0.0.10`), gateway (`10.0.0.1`), bridge (`vmbr0`),
  hostname, or DNS settings.
- Changing the router, DHCP, or the DNS listening mode (already `all`).
- Deploying to the live host; the role reconciles on the next run.

## Acceptance criteria

1. **Given** the role defaults and the Pi-hole vars file, **when** rendered,
   **then** `ip_address` is `10.0.0.10/8` (not `/24`).
2. **Given** the runbook, **when** read, **then** it documents the `pct set`
   `--net0` command and the container restart needed to apply the netmask to an
   existing container.
3. **Given** the documentation, **when** read, **then**
   `ansible/docs/proxmox-pihole-lxc.md` and `docs/pihole-dns.md` show the `/8`
   netmask.
4. **Given** focused validation, **when** it runs, **then** it confirms the `/8`
   netmask in the vars file and role defaults.

## Constraints

- Use the existing `proxmox_lxc` role and `pct` commands; do not add new tooling.
- Keep the container's IP, gateway, bridge, and all other settings unchanged.
- **ASSUMPTION:** the lab is a flat `10.0.0.0/8` L2 (router LAN `10.0.0.0/8`,
  gateway `10.0.0.1`), evidenced by `hermes` at `10.0.10.1/8` and the
  `10.0.0.0/8` Traefik allowlists. If the router actually routes between
  `10.0.0.0/24` and `10.0.10.0/24` as separate L2 segments, a `/8` netmask is
  wrong and would break replies to `10.0.10.x`; the operator must confirm the
  topology before applying.
- **ASSUMPTION:** applying the change to the live container is acceptable via a
  playbook run (which restarts Pi-hole); runtime access is not requested here.

## Plan and rollback

1. Change `ip_address` to `10.0.0.10/8` in
   `ansible/vars/memex-pihole-lxc.yml` and
   `ansible/playbooks/roles/proxmox_lxc/defaults/main.yml`.
2. Document the `pct set --net0` + restart apply step in
   `ansible/docs/proxmox-pihole-lxc.md`.
3. Update `docs/pihole-dns.md` to show the `/8` netmask.
4. Add a focused test asserting the `/8` netmask in the vars file and defaults.
5. Rollback by reverting to `10.0.0.10/24` and rerunning the role (or `pct set`
   back to `/24`).

## Open questions

- Confirm the router routes or bridges between `10.0.0.0/24` and `10.0.10.0/24`.
  **ASSUMPTION:** it bridges (flat `/8`); if it routes, keep `/24`.
