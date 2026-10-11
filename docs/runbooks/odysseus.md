# Odysseus administrator access and recovery

The `odysseus-admin-credentials` Secret in namespace `odysseus` is operator-held
credential escrow. It is not mounted into the application. The Odysseus
Deployment mounts its persistent volume at `/app/data`; `auth.json` and other
application state there are authoritative.

## Retrieve the escrowed login

Run these commands only from a trusted operator workstation with authorized
cluster access. They print the credential to the terminal; do not paste it into
chat, tickets, shell history, or logs:

```sh
kubectl -n odysseus get secret odysseus-admin-credentials \
  -o jsonpath='{.data.username}' | base64 --decode; printf '\n'
kubectl -n odysseus get secret odysseus-admin-credentials \
  -o jsonpath='{.data.password}' | base64 --decode; printf '\n'
```

This Secret is escrow, not synchronization: changing the password in Odysseus
does not update it. The stored password may therefore be stale. If the app
password changes, reseal the new value using the procedure below.

## Locked-out administrator recovery (unsupported manual procedure)

There is no documented upstream admin-reset command. Editing `/app/data/auth.json`
directly is unsupported and is a high-risk manual state mutation. Prefer
upstream-supported recovery if it becomes available. Do not disable
authentication, enable a localhost bypass, delete the admin, remove other users,
or delete/replace application data. Preserve all account metadata and all other
data; the only allowed account-state changes are the existing admin's password
hash and clearing persisted sessions.

Stop if the auth-file structure, password-hash format, or session representation
cannot be identified with certainty from the pinned application implementation.
Do not improvise a hash or edit unrelated JSON fields. Have a verified known-good
credential ready before beginning.

1. Confirm the target and current pod; do not run a shell command that prints
   `auth.json` or credential values into logs:

   ```sh
   kubectl -n odysseus get deploy odysseus
   kubectl -n odysseus get pods -l app=odysseus
   ```

2. Back up the file from the running app container to a protected local path
   before any edit. Replace `<pod>` with the verified pod name. Keep the backup
   out of Git and restrict access to it:

   ```sh
   umask 077
   kubectl -n odysseus exec <pod> -c odysseus -- \
     cat /app/data/auth.json > ./odysseus-auth.json.backup
   test -s ./odysseus-auth.json.backup
   ```

3. Perform the change only against the backed-up file in a controlled local
   working location: preserve its structure, all account metadata and every
   other file/data item; update only the existing admin password hash to the
   verified replacement hash and clear persisted sessions. Validate that the
   result parses and differs only in those permitted fields. If this cannot be
   proven, stop and restore the untouched backup; do not proceed. Never use an
   auth bypass or remove user data as a workaround.

4. Copy the validated file back to the same path and verify the copied file
   parses without printing its contents. This replaces only `auth.json` on the
   existing PVC:

   ```sh
   kubectl -n odysseus cp ./auth.json <pod>:/app/data/auth.json -c odysseus
   kubectl -n odysseus exec <pod> -c odysseus -- \
     python -c 'import json; json.load(open("/app/data/auth.json"))'
   ```

5. Restart and verify the rollout, then verify login with the replacement
   credential and confirm existing account/data remain present:

   ```sh
   kubectl -n odysseus rollout restart deployment/odysseus
   kubectl -n odysseus rollout status deployment/odysseus --timeout=5m
   kubectl -n odysseus get pods -l app=odysseus
   ```

   If the rollout or login fails, stop; retain the backup and recover without
   deleting or recreating the PVC.

6. Once verified, reseal the replacement credential through GitOps. Keep the
   local plaintext Secret file private and remove it after sealing:

    ```sh
    set +x                         # do not run with shell tracing
    umask 077
    work=$(mktemp -d)
    read -r -p 'Admin username: ' username
    read -r -s -p 'New admin password: ' password
    printf '\n'
    printf '%s' "$username" > "$work/username"
    printf '%s' "$password" > "$work/password"
    unset username password
    kubectl -n odysseus create secret generic odysseus-admin-credentials \
      --dry-run=client -o yaml \
      --from-file=username="$work/username" \
      --from-file=password="$work/password" \
      > "$work/odysseus-admin-credentials.secret.yaml"
    kubeseal --controller-name sealed-secrets-controller \
      --controller-namespace sealed-secrets --format yaml \
      < "$work/odysseus-admin-credentials.secret.yaml" \
      > gitops/sealed/odysseus/admin-credentials.yaml
    rm -rf "$work"
    ```

   Review that the manifest is a strict-scope SealedSecret named
   `odysseus-admin-credentials` in namespace `odysseus`; never display or commit
   the plaintext file. Commit and push only the SealedSecret, allowing Argo CD
   to reconcile it. Verify reconciliation and the Secret's key names without
   displaying values:

   ```sh
   git add gitops/sealed/odysseus/admin-credentials.yaml
   git commit -m "seal Odysseus admin credentials"
   git push
   kubectl -n odysseus get sealedsecret odysseus-admin-credentials
   kubectl -n odysseus get secret odysseus-admin-credentials \
     -o jsonpath='{.data}' | python3 -c 'import json,sys; print(sorted(json.load(sys.stdin).keys()))'
   ```

The canonical sealing guidance is [Sealing secrets](../sealing-secrets.md).
Do not apply a plaintext Secret or edit the live Secret by hand; Argo CD and the
strict-scope SealedSecret remain the declarative source of truth.
