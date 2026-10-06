# Pi-hole query logging and private-network recognition

## Goal

Configure the Ansible-managed Pi-hole to retain query logging and recognize
addresses in `10.0.0.0/8` as local, resolving the observed dnsmasq
"outside network" warnings without weakening unrelated DNS behavior.

## User-visible behavior

- Pi-hole query logging is enabled in installer settings and Pi-hole FTL v6.
- dnsmasq considers the complete RFC1918 `10.0.0.0/8` range local for private
  reverse lookups, so reverse queries in the range do not produce outside-
  network warnings.
- Existing local DNS, wildcard, upstream forwarding, and blocking behavior is
  preserved.

## Non-goals

- Changing upstream resolvers, DNSSEC, blocking, or query privacy level.
- Changing network/router DHCP or Pi-hole's installation address.
- Deploying changes to the live host; this change only updates repository
  configuration.

## Acceptance criteria

1. **Given** the default role configuration, **when** rendered/applied,
   **then** both installer `QUERY_LOGGING` and FTL `dns.queryLogging` are true.
2. **Given** a DNS reverse lookup address within `10.0.0.0/8`, **when** FTL
   processes it, **then** the `10.0.0.0/8` network is explicitly configured as
   local to dnsmasq and does not trigger an outside-network rejection.
3. **Given** existing `dnsmasq_lines`, **when** the role applies the desired
   local-network and wildcard settings, **then** it preserves all existing
   entries, adds missing desired entries, and does not duplicate entries on
   subsequent runs.
4. **Given** the rendered role defaults and template, **when** focused
   validation runs, **then** it confirms the two logging values and the exact
   local CIDR configuration.

## Constraints

- Use the existing Pi-hole Ansible role and Pi-hole v6 FTL configuration
  mechanism (`pihole-FTL --config`).
- Keep the memory-lean FTL profile, changing only the logging value needed.
- dnsmasq's `local` domain configuration must use `local=/10.in-addr.arpa/` or
  the supported Pi-hole v6 equivalent; verify the selected setting against
  repository patterns before implementing.
- **ASSUMPTION:** “log everything” means enable the existing Pi-hole query log
  and FTL query logging, not disable privacy safeguards or increase retention.
- **ASSUMPTION:** “10./8” refers to all of `10.0.0.0/8`; preserve `10.0.0.0/8`
  notation in behavior and document the corresponding reverse-DNS scope.
- **ASSUMPTION:** The supplied URL identifies the managed Pi-hole, but runtime
  access/deployment is not requested; do not contact or modify the live service.

## Plan and rollback

1. Set the role default and FTL profile logging values to true.
2. Add a default dnsmasq local-network setting through the role's existing
   `misc.dnsmasq_lines` mechanism, without replacing wildcard entries.
3. Update role documentation as needed and validate generated values/config.
4. Rollback by reverting these configuration/documentation edits and rerunning
   the role; the current values (`false`, no RFC1918 reverse-local rule) return.

## Open questions

- None blocking. **ASSUMPTION:** retain the current 7-day database retention
  because no retention period was requested.
