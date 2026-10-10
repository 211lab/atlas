# Pi-hole full query logging (domains + client IPs)

## Goal

Make the Ansible-managed Pi-hole record every DNS query with **both** the queried
domain and the originating client address, so the query log and dashboards show
per-device, per-domain detail. Today the role sets `misc.privacylevel: 2`, which
per Pi-hole stores domains as `hidden` and clients as `0.0.0.0` — exactly the two
fields the operator needs. Full detail is privacy level `0`.

## User-visible behavior

- The Pi-hole query log shows the queried domain and the real client IP for every
  query.
- Top Domains, Top Clients, and Clients-over-time are populated.
- `dns.queryLogging` remains true; retention and the rest of the memory-lean
  profile are unchanged.
- The role verifies the applied privacy level and listening mode after applying
  them and fails loudly if they did not take effect (so a silent no-op like the
  earlier listening-mode miss is caught).

## Non-goals

- Changing retention (`database.maxDBdays` stays 7).
- Changing listening mode (already `all`), upstreams, blocking, DNSSEC, or cache
  size.
- Deploying to the live host; this change only updates repository configuration.

## Acceptance criteria

1. **Given** the role defaults, **when** rendered, **then** `misc.privacylevel`
   is `0` (show everything) and `dns.queryLogging` is `true`.
2. **Given** an existing install, **when** the role runs, **then** it applies
   `misc.privacylevel` through the existing `pihole-FTL --config` read/apply loop
   and restarts FTL only when the value changes.
3. **Given** the role runs, **when** the FTL settings have been applied, **then**
   it asserts that `dns.listeningMode` equals the desired uppercase mode and
   `misc.privacylevel` equals `0`, failing with a clear message otherwise.
4. **Given** focused validation, **when** it runs, **then** it confirms
   `misc.privacylevel` is `0`, `dns.queryLogging` is `true`, and the memory-lean
   entries remain.
5. **Given** the documentation, **when** read, **then**
   `ansible/docs/proxmox-pihole-lxc.md` and `docs/pihole-runbook.md` describe
   `misc.privacylevel 0` and `dns.queryLogging true`.

## Constraints

- Use the existing Pi-hole Ansible role and the Pi-hole v6 FTL configuration
  mechanism (`pihole-FTL --config`); do not add new tooling.
- Keep the memory-lean FTL profile; change only the privacy level and add the
  assertion.
- **ASSUMPTION:** privacy level `0` intentionally disables the privacy safeguard
  (domains and clients are stored in full). This supersedes the earlier
  assumption in `docs/specs/pihole-logging-network.md` that "log everything"
  would not disable privacy safeguards; the operator has now explicitly asked
  for domain + client detail.
- **ASSUMPTION:** "all logs" means full per-query detail, not longer retention;
  `database.maxDBdays` stays `7`. Flag if a longer window is wanted.
- **ASSUMPTION:** runtime access/deployment is not requested; do not contact or
  modify the live Pi-hole.

## Plan and rollback

1. Change `misc.privacylevel` from `2` to `0` in
   `roles/pihole/defaults/main.yml`.
2. Add a post-apply assertion task in `roles/pihole/tasks/main.yml` that re-reads
   `dns.listeningMode` and `misc.privacylevel` and asserts the desired values.
3. Update `ansible/docs/proxmox-pihole-lxc.md` and `docs/pihole-runbook.md`.
4. Extend the focused test to cover the privacy level and query logging.
5. Rollback by reverting these edits and rerunning the role; privacy level `2`
   returns.

## Open questions

- Retention: keep the 7-day window? **ASSUMPTION:** yes, unless a longer history
  is requested.
