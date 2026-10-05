# Sealing secrets (cluster admin)

How to add or change a Kubernetes Secret in the Atlas GitOps repo without ever
committing plaintext. Secrets are committed as **SealedSecrets** — encrypted
with the cluster controller's public key — so git stays the single source of
truth and the repository is safe to share.

- Controller: `sealed-secrets-controller` in namespace `sealed-secrets`
  (chart `bitnamicharts/sealed-secrets`, shown in
  [GitOps platform](gitops-platform.md)).
- Client: `kubeseal` (0.40.0 in the lab).
- Committed secrets live in `gitops/sealed/*.yaml`.

## Prerequisites (cluster admin)

- `kubectl` pointed at the cluster: `KUBECONFIG=~/.kube/atlas-admin.yaml`.
- `kubeseal` on `PATH`.
- A checkout of this repo (`atlas-admin/atlas`) with push access over SSH
  (`git.atlas.lan:2222`).

Only the controller can decrypt; anyone can encrypt with its public cert.
Sealing does **not** require cluster write access — only applying does.

## The canonical workflow

### 1. Build the plaintext Secret (locally, never committed)

```sh
kubectl -n <namespace> create secret generic <name> \
  --dry-run=client -o yaml \
  --from-literal=KEY1='value1' \
  --from-file=KEY2=./some-file \
  > /tmp/<name>.secret.yaml
```

Use `--dry-run=client -o yaml` so nothing touches the cluster. Do **not**
`kubectl apply` the plaintext Secret and do **not** commit it.

### 2. Seal it against the controller

```sh
kubeseal \
  --controller-name sealed-secrets-controller \
  --controller-namespace sealed-secrets \
  --format yaml \
  < /tmp/<name>.secret.yaml \
  > gitops/sealed/<name>.yaml
```

`kubeseal` reads the live controller's certificate by default. To seal offline
(no cluster access), fetch the cert once and pass `--cert`:

```sh
kubeseal --fetch-cert \
  --controller-name sealed-secrets-controller \
  --controller-namespace sealed-secrets \
  > atlas-sealed-secrets.pem

kubeseal --cert atlas-sealed-secrets.pem --format yaml \
  < /tmp/<name>.secret.yaml > gitops/sealed/<name>.yaml
```

### 3. Commit and apply

```sh
git add gitops/sealed/<name>.yaml
git commit -m "seal <name>"
git push

# Apply directly, or let the owning Application reconcile it.
kubectl apply -f gitops/sealed/<name>.yaml
```

If the SealedSecret is listed by an Argo CD Application's path, Argo creates the
Secret on the next sync (the Gitea webhook fires it, 60s poll as fallback).
Applying by hand makes it live immediately and is idempotent.

### 4. Verify

```sh
# The controller decrypts on apply; a bad seal leaves STATUS empty or UnsealFailed.
kubectl -n <namespace> get sealedsecret <name> -o jsonpath='{.status.conditions[0].message}{"\n"}'

# The real Secret exists and carries the keys (values masked here).
kubectl -n <namespace> get secret <name> -o jsonpath='{.data}' \
  | python3 -c "import json,sys;print(sorted(json.load(sys.stdin).keys()))"
```

Delete the temporary plaintext file when done: `rm /tmp/<name>.secret.yaml`.

## Scopes

`kubeseal` binds a SealedSecret to a namespace and name by default. Choose the
narrowest that works:

| Scope | Flag | Decrypts as | Use when |
| --- | --- | --- | --- |
| **strict** (default) | *(none)* | exactly `<name>` in the sealed namespace | almost always |
| namespace-wide | `--namespace <ns>` | any Secret in `<ns>` with any name | the name is chosen at deploy time |
| cluster-wide | `--scope cluster-wide` | any name, any namespace | a shared credential across namespaces |

Prefer **strict**. If a deploy fails with `ErrUnsealFailed` /
`no key could decrypt secret`, the scope or name does not match the target
Secret.

## Re-sealing when a value changes

There is no way to edit a SealedSecret in place — re-seal it. Same workflow,
overwriting the committed file:

1. Build the new plaintext Secret (step 1).
2. Seal it over `gitops/sealed/<name>.yaml` (step 2).
3. Commit, push, and apply (step 3).
4. Restart the consuming workload if it reads the Secret as an env var at start
   (a mounted Secret updates in place; an env var does not):

   ```sh
   kubectl -n <namespace> rollout restart deploy/<workload>
   ```

Set the SealedSecret's `metadata.name`/`namespace` to the **real** Secret name
and namespace, not the workload's — the SealedSecret's `template` is what the
controller materializes.

## Adding a new secret and consuming it

1. Seal it (above) into `gitops/sealed/<name>.yaml`.
2. Reference it from the chart or Application that owns the namespace:
   - As env vars: `valueFrom.secretKeyRef {name, key}`.
   - As a mount: a `volumes` entry with `secret.secretName`.
3. Commit; Argo reconciles. Do not add a plaintext Secret manifest anywhere.

## Sealing key management (cluster admin)

The controller holds the private keys that decrypt every SealedSecret. Losing
them means every committed SealedSecret is undecryptable — treat the key like a
root credential.

```sh
# The active signing key (name carries a random suffix).
kubectl -n sealed-secrets get secret \
  -l sealedsecrets.bitnami.com/sealed-secrets-key=active -o name
```

- **Back it up** out of band (a password manager or encrypted offline store),
  never to this repo:

  ```sh
  kubectl -n sealed-secrets get secret \
    -l sealedsecrets.bitnami.com/sealed-secrets-key=active -o yaml \
    > atlas-sealed-secrets-key.backup.yaml   # store securely; do not commit
  ```

- **Rotate** by adding a new key (`--key-prefix sealed-secrets-controller-key`)
  and deleting the old one once re-sealed. Rotating a key does not re-encrypt
  existing SealedSecrets — they keep decrypting with the key that sealed them
  until that key is removed, so re-seal and re-apply every secret before retiring
  a key.
- **Recover** by restoring the backed-up key Secret into `sealed-secrets` and
  restarting the controller.

## Worked example: re-sealing `redop-postgres`

A production Postgres password contained a `/`, which percent-encoded to `%2F`
in `DATABASE_URL` and broke both psycopg and alembic. The fix was a URL-safe
password, re-sealed and applied:

```sh
# 1. New value.
NEWPW=$(openssl rand -hex 24)
kubectl -n redop exec deploy/redop-postgres -- \
  psql -U redops -d redops -c "ALTER USER redops WITH PASSWORD '$NEWPW';"

# 2. Plaintext Secret from the live values (never committed).
kubectl -n redop create secret generic redop-postgres \
  --dry-run=client -o yaml \
  --from-literal=DATABASE_URL="postgresql://redops:${NEWPW}@redop-postgres:5432/redops" \
  --from-literal=POSTGRES_PASSWORD="$NEWPW" \
  > /tmp/redop-postgres.secret.yaml

# 3. Seal over the committed file, commit, apply.
kubeseal --controller-name sealed-secrets-controller \
  --controller-namespace sealed-secrets --format yaml \
  < /tmp/redop-postgres.secret.yaml > gitops/sealed/redop-postgres.yaml
git commit -am "fix(redop): re-seal redop-postgres" && git push
kubectl apply -f gitops/sealed/redop-postgres.yaml
```

Because the API reads `DATABASE_URL` as an env var, the fix took effect on the
next `rollout restart` / deploy of `redop-api`.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `SealedSecret` STATUS empty, no Secret created | controller has no matching key | re-seal against the current controller cert |
| `ErrUnsealFailed` / `no key could decrypt secret` | scope/name/namespace mismatch | re-seal with the target's exact name/namespace (or widen the scope) |
| Secret created but key missing | `--from-literal`/`--from-file` omitted | rebuild the plaintext Secret with every key, re-seal |
| App still uses the old value | env var read at start | `kubectl rollout restart` the workload |
| `kubeseal: cannot fetch certificate` | controller not reachable / wrong name | pass `--controller-name`/`--controller-namespace`, or seal with `--cert` |

## Rules

- **Never commit a plaintext Secret**, and never `kubectl apply` one. Only
  `gitops/sealed/*.yaml` is committed.
- **Seal against the live controller cert**, or a fetched cert kept out of git.
- **Prefer the strict scope**; widen only when the name is not known at seal
  time.
- **Back up the sealing key** out of band; it is the root of every committed
  secret.
- Do not paste secret values into issues, chat, or logs; re-seal from the source
  of truth instead.
