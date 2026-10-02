# SSH Config From Inventory

Update local `~/.ssh/config` so host aliases match Ansible inventory host
names and default to `root`.

## Purpose

- Keep SSH aliases aligned with `atlas/inventory.yml`
- Use inventory host aliases with explicit SSH username
- Rebuild only a managed section in `~/.ssh/config`

## Prerequisites

- Run from [`atlas`](/home/wsl/211-lab/atlas) directory
- `ansible-inventory` installed
- `jq` installed

## Runbook

1. Back up your existing SSH config:

```sh
cp ~/.ssh/config ~/.ssh/config.bak.$(date +%Y%m%d-%H%M%S)
```

2. Create/update a managed block from inventory:

```sh
mkdir -p ~/.ssh
tmp_cfg="$(mktemp)"

{
  echo '# BEGIN ATLAS MANAGED HOSTS'
  ansible-inventory -i inventory.yml --list \
    | jq -r '
        ._meta.hostvars
        | to_entries[]
        | "Host \(.key)\n  HostName \(.value.ansible_host // .key)\n  User root\n  BatchMode no\n"
      '
  echo '# END ATLAS MANAGED HOSTS'
} > "$tmp_cfg"
```

3. Replace prior managed section (if present), then append fresh section:

```sh
cfg=~/.ssh/config
[ -f "$cfg" ] || touch "$cfg"

awk '
  BEGIN { skip=0 }
  /^# BEGIN ATLAS MANAGED HOSTS$/ { skip=1; next }
  /^# END ATLAS MANAGED HOSTS$/ { skip=0; next }
  !skip { print }
' "$cfg" > "${cfg}.clean"

cat "${cfg}.clean" "$tmp_cfg" > "$cfg"
chmod 600 "$cfg"
rm -f "${cfg}.clean" "$tmp_cfg"
```

4. Validate:

```sh
ssh -G turing | rg '^(hostname|user|identityfile) '
```

You should see:

- `hostname 10.0.0.101` (or current inventory IP)
- `user root`
