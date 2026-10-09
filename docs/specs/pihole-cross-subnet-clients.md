# Pi-hole cross-subnet client recognition

## Goal

Make the Ansible-managed Pi-hole answer DNS queries from clients that are **not**
on Pi-hole's own subnet, so the Pi-hole query log attributes queries to the real
client address instead of the router. The lab is a routed `10.0.0.0/8` network:
Pi-hole is at `10.0.0.10` (`10.0.0.0/24`) while WiFi clients live at
`10.0.10.0/24` and reach Pi-hole through the router at `10.0.0.1`.

## User-visible behavior

- Pi-hole accepts and answers DNS queries from off-subnet clients (e.g.
  `10.0.10.x`) that are routed to it, instead of dropping them as
  non-local requests.
- The Pi-hole query log shows the real client address for those queries, so
  per-client blocking/grouping and dashboards work.
- The listening mode is a single role variable, applied both to fresh installs
  (installer `DNSMASQ_LISTENING`) and to existing installs (Pi-hole v6
  `dns.listeningMode`).
- Existing local DNS records, wildcard resolution, upstream forwarding,
  blocking, and query logging are preserved.

## Non-goals

- Changing the router's DHCP scope, DNS advertisement, or NAT/routing behavior.
  The router must still hand out `10.0.0.10` as DNS and must **route** (not
  masquerade) between `10.0.10.0/24` and `10.0.0.0/24`; that is an operator step
  documented, not automated, here.
- Making Pi-hole the DHCP server. DHCP broadcasts do not cross the router, so
  Pi-hole DHCP cannot serve the `10.0.10.0/24` WiFi scope without a relay.
- Changing Pi-hole's address, upstreams, DNSSEC, blocking, or privacy level.
- Deploying to the live host; this change only updates repository configuration.

## Acceptance criteria

1. **Given** the role defaults, **when** rendered, **then** a
   `pihole_listening_mode` variable exists and defaults to `all` (permit all
   origins), and the FTL setting `dns.listeningMode` is set to its uppercase
   form (`ALL`).
2. **Given** a fresh install, **when** `setupVars.conf.j2` is rendered, **then**
   `DNSMASQ_LISTENING` is driven by `pihole_listening_mode` (not hard-coded
   `local`).
3. **Given** an existing install, **when** the role runs, **then** it applies
   `dns.listeningMode` through the existing `pihole-FTL --config` read/apply
   mechanism and restarts FTL only when the value changes.
4. **Given** the role defaults, **when** focused validation runs, **then** it
   confirms the default listening mode, the uppercase FTL value, the template
   binding, and that the FTL settings list still contains the memory-lean
   profile entries.
5. **Given** the documentation, **when** read, **then** `docs/pihole-dns.md`
   and `docs/pihole-runbook.md` state the cross-subnet requirement, the
   listening-mode change, and the router NAT-vs-route caveat.

## Constraints

- Use the existing Pi-hole Ansible role and the Pi-hole v6 FTL configuration
  mechanism (`pihole-FTL --config`); do not add new tooling.
- Keep the memory-lean FTL profile; only add the listening-mode entry.
- The installer expects lowercase (`local`/`single`/`bind`/`all`); Pi-hole v6
  `dns.listeningMode` expects uppercase (`LOCAL`/`SINGLE`/`BIND`/`ALL`). Store
  the lowercase form in the variable and uppercase it for FTL.
- **ASSUMPTION:** default `all` (permit all origins) is correct for this lab
  because tailnet clients reach Pi-hole on a non-`eth0` interface; `single`
  would restrict answers to `eth0` and break tailnet resolution. Document the
  tradeoff.
- **ASSUMPTION:** the router already routes (not NATs) between the two subnets;
  if it NATs, no Pi-hole change can recover the client IP and the operator must
  fix the router. This is documented, not enforced.
- **ASSUMPTION:** runtime access/deployment is not requested; do not contact or
  modify the live Pi-hole.

## Plan and rollback

1. Add `pihole_listening_mode: all` to `roles/pihole/defaults/main.yml` and add
   `{ key: "dns.listeningMode", value: "{{ pihole_listening_mode | upper }}" }`
   to `pihole_ftl_settings`.
2. Bind `DNSMASQ_LISTENING` in `templates/setupVars.conf.j2` to the variable.
3. Add a focused test `tests/validate_cross_subnet_clients.py`.
4. Update `docs/pihole-dns.md` (§1.4) and `docs/pihole-runbook.md` (Phase 5 and
   troubleshooting) with the cross-subnet requirement and NAT caveat.
5. Rollback by reverting these edits and rerunning the role; the previous
   `local` listening mode returns.

## Open questions

- None blocking. **ASSUMPTION:** the operator will confirm the router routes
  rather than NATs; the `dig @10.0.0.10` test in the docs distinguishes the two.
