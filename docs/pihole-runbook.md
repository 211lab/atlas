# Pi-hole DNS runbook — provision, wire, and verify

> Operational runbook for the dedicated Pi-hole and automatic Ingress DNS
> registration. Design and rationale live in [ADR 0001](adr/0001-service-naming-and-reachability.md)
> (accepted) and [Dedicated Pi-hole DNS](pihole-dns.md). This page is the
> step-by-step execution order, its verification, and its rollback.
>
> **Status:** live. The Pi-hole LXC (`10.0.0.10`, unprivileged on `memex`)
> is provisioned, `gitops/sealed/pihole-api.yaml` is sealed with the real app
> password, and ExternalDNS writes Ingress hosts into it. `*.atlas.lan`
> resolves network-wide via Pi-hole, in-cluster via CoreDNS, and (as a fallback)
> via workstation `/etc/hosts` entries.

## Outcome

After this runbook: every device that uses the Pi-hole resolves `*.atlas.lan`,
and each Ingress host is registered automatically as it is deployed.

```
Ingress created ──▶ ExternalDNS reads Ingress + Traefik Service ──▶ Pi-hole webhook
                                                                    │  A record
LAN/tailnet clients ◀── Pi-hole answers app.atlas.lan ──────────────┘
```

## Inventory and preconditions

| Item | Value | Where |
| --- | --- | --- |
| Pi-hole host | `pihole` / `10.0.0.10` | `inventory.yml` (`dns` group) |
| Hostname | `pihole.atlas.lan` | `pihole_hostname` default |
| Cluster | k3s, Traefik on `10.0.0.110-113` | `KUBECONFIG=~/.kube/atlas-admin.yaml` |
| GitOps | Argo CD app-of-apps `root` from Gitea `atlas-admin/atlas` | `gitops/apps/` |
| Tools | `ansible`, `kubectl`, `kubeseal`, `gh` | workstation |

Preflight:

```sh
ansible all -i inventory.yml -l dns -m ping -o          # once the host exists
export KUBECONFIG=~/.kube/atlas-admin.yaml
kubectl -n argocd get application external-dns 2>/dev/null || echo "not deployed yet"
kubeseal --fetch-cert --controller-name sealed-secrets-controller \
  --controller-namespace sealed-secrets >/dev/null && echo "kubeseal can reach the controller"
```

## Phase 1 — Provision the Pi-hole

The host is an unprivileged LXC container on the `memex` Proxmox host
(`10.0.0.10`, Debian 12). Creation is automated; see
[Proxmox Pi-hole LXC](pihole-dns.md#12-create-the-container-and-bootstrap-access) for the container
spec and the memory-lean profile. The container is created with the `control`
public key already installed for `root`.

```sh
# 1. Create and start the LXC on memex (resources/address in the vars file).
ansible-playbook ansible/playbooks/proxmox-create-pihole-lxc.yml \
  -e @ansible/vars/memex-pihole-lxc.yml -l memex

# 2. Bootstrap the control user inside the container (root, key auth).
ansible-playbook ansible/playbooks/bootstrap-control.yaml -l dns -u root

# 3. Install and configure Pi-hole; supply the admin password from a secret
#    manager, never shell history.
ansible-playbook ansible/playbooks/pihole.yaml \
  -e pihole_webpassword="$PIHOLE_ADMIN_PASSWORD" \
  -e 'pihole_local_records=[{"ip":"10.0.0.10","names":["pihole.atlas.lan","dns.atlas.lan"]},{"ip":"10.0.0.1","names":["router.lan","gw.lan"]}]'

# 4. Verify the resolver answers.
dig +short @10.0.0.10 pihole.atlas.lan
dig +short @10.0.0.10 github.com      # forwarded upstream
```

Notes:

- The role installs Pi-hole v6 unattended, is idempotent, and bakes in a
  memory-lean FTL profile (`dns.cache.size 2000`, `database.maxDBdays 7`,
  `dns.queryLogging true`, `misc.privacylevel 0`, `webserver.threads 10`).
- The Pi-hole **app password** (Settings → API) is what ExternalDNS uses; it is
  the same value as the admin password supplied above.

## Phase 2 — Seal the Pi-hole API password

Replace the committed placeholder with a real SealedSecret (safe to commit):

```sh
kubectl -n external-dns create secret generic pihole-api \
  --dry-run=client -o yaml \
  --from-literal=password="$PIHOLE_API_PASSWORD" \
| kubeseal --controller-name sealed-secrets-controller \
    --controller-namespace sealed-secrets --format yaml \
> gitops/sealed/pihole-api.yaml
```

If the `external-dns` namespace does not exist yet, create it first or seal with
`--namespace external-dns` and apply after Argo creates it.

## Phase 3 — Make the Pi-hole reachable from the cluster

ExternalDNS runs in-cluster and calls the Pi-hole API. Pick one:

- **Option A (readable, recommended):** add the Pi-hole to the CoreDNS custom
  zone `gitops/manifests/coredns-atlas.yaml`:

  ```yaml
  atlas.server: |
      atlas.lan:53 {
          hosts {
              10.43.186.184 git.atlas.lan registry.atlas.lan argocd.atlas.lan
              10.0.0.10    pihole.atlas.lan
              fallthrough
          }
      }
  ```

- **Option B:** set `PIHOLE_SERVER: "http://10.0.0.10"` in
  `helm/values/external-dns.yaml` (removes the DNS dependency).

## Phase 4 — Deploy ExternalDNS through GitOps

`gitops/apps/external-dns.yaml` and `helm/values/external-dns.yaml` already
declare it (chart `kubernetes-sigs/external-dns` `1.23.0`, provider `webhook`
via `ghcr.io/tarantini-io/external-dns-pihole-webhook:v1.0.0`,
`domainFilters: [atlas.lan]`, `policy: upsert-only`, `registry: noop`,
`sources: [ingress, service]`).
Commit Phases 2–3, then push to **both** remotes — Argo CD watches the forge:

```sh
git add gitops/sealed/pihole-api.yaml gitops/manifests/coredns-atlas.yaml helm/values/external-dns.yaml
git commit -m "feat(dns): provision Pi-hole credentials and in-cluster resolution"
git push origin main
git push gitea main        # local forge → Gitea webhook → Argo CD
```

Verify:

```sh
kubectl -n argocd get application external-dns \
  -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status
kubectl -n external-dns get pods
kubectl -n external-dns logs deploy/external-dns --tail=50
```

If it does not appear within a minute, force a refresh:

```sh
kubectl -n argocd annotate application root         argocd.argoproj.io/refresh=hard --overwrite
kubectl -n argocd annotate application external-dns argocd.argoproj.io/refresh=hard --overwrite
```

## Phase 5 — Cut the network over to Pi-hole

1. **Router / DHCP:** advertise `10.0.0.10` as the primary DNS server (public
   resolver only as fallback); reserve the Pi-hole's IP.
2. **Pi-hole upstreams:** keep public resolvers so non-lab names resolve.
3. **Tailnet:** `memex` already advertises `10.0.0.0/8` into the tailnet, so
   Pi-hole is reachable at `10.0.0.10`. Add it in the Tailscale admin console
   (**DNS → Nameservers**, split DNS for `atlas.lan`, or a global nameserver with
   "Override local DNS"). See
   [DNS in the Atlas lab → Tailnet access](atlas-dns.md#part-3--tailnet-access).
4. **Cross-subnet clients:** for clients on a different subnet than Pi-hole
   (e.g. WiFi `10.0.10.0/24`), the router must route (not NAT) to
   `10.0.0.0/24` and hand out `10.0.0.10` as DNS; Pi-hole's
   `pihole_listening_mode` must be `all` (not `local`) to answer them.

## Phase 6 — Verify end to end

```sh
# A record written from an Ingress host:
dig +short @10.0.0.10 redop.atlas.lan
dig +short @10.0.0.10 git.atlas.lan

# From a client that uses Pi-hole as its resolver:
dig +short redop.atlas.lan

# HTTPS still terminates at Traefik:
curl -ksS -o /dev/null -w '%{http_code}\n' --resolve redop.atlas.lan:443:10.0.0.110 https://redop.atlas.lan/
```

Success = ExternalDNS `Synced/Healthy`, `dig` returns a Traefik node IP, and the
endpoint returns 200.

## Phase 7 — Troubleshooting

| Symptom | Check / fix |
| --- | --- |
| ExternalDNS `Degraded`, logs show auth failure | `pihole-api` still the placeholder, or the app password changed. Re-run Phase 2. |
| `dial tcp: lookup pihole.atlas.lan` in logs | Phase 3 not applied, or CoreDNS not reloaded. Add the record or use Option B. |
| No records created | `dig @10.0.0.10` for the host; check ExternalDNS logs for `domainFilters`/ownership; confirm `sources` include `ingress`. |
| Records point at wrong IPs | Traefik Service status changed; re-check `kubectl -n kube-system get svc traefik`. |
| Records deleted unexpectedly | Not possible with `policy: upsert-only`; ExternalDNS never prunes. Static records are also safe. |
| In-cluster names fail | CoreDNS `coredns-custom` (Phase 3) is separate from the Pi-hole; verify both. |
| WSL `*.atlas.lan` unresolved | Add entries to `/etc/hosts` (see below) or point the workstation at Pi-hole. |
| Pi-hole shows the router (`10.0.0.1`) instead of WiFi clients | Clients are off-subnet; set `pihole_listening_mode: all` and confirm the router routes (not NATs) between subnets; verify with `dig @10.0.0.10` from a WiFi client and the query log. |

Workstation fallback (`/etc/hosts`), until Pi-hole is the resolver:

```text
10.0.0.110 git.atlas.lan registry.atlas.lan argocd.atlas.lan redop.atlas.lan immich.atlas.lan
10.0.0.10 pihole.atlas.lan
```

On WSL, `/etc/hosts` is regenerated on boot; set `[network] generateHosts=false`
in `/etc/wsl.conf` (then `wsl --shutdown`) to persist manual entries.

## Phase 8 — Rollback / disable

- Stop the automation: delete `gitops/apps/external-dns.yaml`, commit, and push
  to the forge. Argo prunes the ExternalDNS Application.
- Delete leftovers in Pi-hole (Settings → Local DNS Records) manually, since
  `upsert-only` does not prune records it created.
- Re-point router/DHCP DNS away from the Pi-hole if decommissioning the host.

## Security

- The Pi-hole app password is a secret: seal it; never commit plaintext.
- Restrict the Pi-hole admin UI to the lab network; do not expose it publicly.
- Keep `domainFilters: [atlas.lan]` so ExternalDNS cannot touch unrelated
  records.
- The webhook provider is third-party; its image is pinned to `v1.0.0` — review
  before bumping.

## Known limitations

- **Single point of failure:** per ADR 0001, one Pi-hole is a SPOF for all
  non-`*.ts.net` resolution; add a second instance for HA.
- `*.atlas.lan` certs come from the internal `atlas-ca`, not a public CA.

## References

- [ADR 0001 — Service naming and reachability](adr/0001-service-naming-and-reachability.md)
- [Dedicated Pi-hole DNS design](pihole-dns.md)
- [Pi-hole v6 docs](https://docs.pi-hole.net/)
- [ExternalDNS](https://github.com/kubernetes-sigs/external-dns) ·
  [Pi-hole webhook provider](https://github.com/tarantini-io/external-dns-pihole-webhook)
