# Atlas Kubernetes control-plane access runbook

> See [C4 architecture](c4-architecture.md) for the full system/container/component/deployment views.

> Scope: Atlas is a four-host Proxmox cluster running a highly available K3s control plane. This is a tailored operational guide. It contains no passwords, private keys, node-join tokens, or kubeconfig credential data.

## Current deployed infrastructure

Verified 2026-10-02 from the Atlas API VIP (`https://10.0.0.108:6443`).

| Component | Status | Source-of-truth detail |
| --- | --- | --- |
| K3s | Deployed | v1.36.3+k3s1: three embedded-etcd control-plane VMs and one worker, all `Ready` |
| Kubernetes API | Deployed | kube-vip virtual IP: https://10.0.0.108:6443 |
| Secret encryption | Deployed | Sealed Secrets encryption at rest |
| Helm releases | Deployed | `atlas-monitoring` (monitoring), `csi-driver-nfs`, `traefik`, `traefik-crd` (kube-system) |
| NFS CSI | Deployed | Driver installed; `truenas-nfs` StorageClass available for platform data (`local-path` remains the cluster default) |
| TrueNAS NFS | Deployed | Dataset `data/atlas-k8s` on 10.0.10.26 exported at `/mnt/data/atlas-k8s` to `10.0.0.0/24,10.0.10.0/24`; consumed via the `truenas-nfs` StorageClass (see GitOps platform runbook). Existing `movies` export left untouched |
| Prometheus and Grafana | Deployed | `atlas-monitoring` kube-prometheus-stack 88.3.0 (app v0.93.0) runs in the monitoring namespace |
| Grafana access | Deployed | Network UI at http://10.0.0.110:3000 with anonymous Viewer access; administrator login remains available |
| K3s VM metrics | Deployed | Node Exporter DaemonSet runs across the K3s nodes |
| Physical PVE metrics | Deployed | Node Exporter runs on all four PVE hosts and Prometheus scrapes the atlas-proxmox-node-exporter job |
| Titan Windows metrics | Pending | Windows Exporter is not installed yet; the installation needs a one-time UAC approval |

## 1. Access model

Atlas has three separate administration layers. A credential for one layer does not automatically grant access to the next.

| Layer | Account or credential | What it administers |
| --- | --- | --- |
| Proxmox | root at a PVE host | Physical PVE host, VMs, storage, networks, and VM power state |
| Guest OS | ubuntu at a K3s VM | Ubuntu VM commands permitted through sudo |
| Kubernetes | Admin kubeconfig | Kubernetes resources, RBAC, workloads, and cluster settings |

This guide assumes:

- You can authenticate as root to the Proxmox hosts when needed.
- The K3s VMs run a guest user with SSH access and passwordless sudo. On the current build that user is `ubuntu`; the `control` service account exists on the Ansible inventory but is not currently authorized for SSH on the K3s VMs.
- You have the appropriate SSH private key on the workstation (`~/.ssh/id_rsa_control`).
- You are using Titan, currently 10.0.10.166, or another system that can reach the Atlas network.
- Passwords and keys are never stored in scripts, Git, shell history, tickets, or this document.

If a VM uses a different guest username, change only the `ControlUser` variable in the examples. Do not use Proxmox root as a Kubernetes credential.

## 2. Atlas topology

### Proxmox and VM placement

| Physical PVE host | PVE management IP | K3s VM | VMID | Guest IP | Kubernetes role |
| --- | ---: | --- | ---: | ---: | --- |
| Turing | 10.0.0.101 | atlas-k3s-cp1 | 201 | 10.0.0.110 | control plane and embedded etcd |
| Hopper | 10.0.0.102 | atlas-k3s-cp2 | 202 | 10.0.0.111 | control plane and embedded etcd |
| Lovelace | 10.0.0.103 | atlas-k3s-cp3 | 203 | 10.0.0.112 | control plane and embedded etcd |
| Babbage | 10.0.0.104 | atlas-k3s-worker1 | 204 | 10.0.0.113 | worker |

### Kubernetes API endpoint

Use this high-availability API endpoint from workstations and automation:

~~~text
https://10.0.0.108:6443
~~~

10.0.0.108 is the kube-vip virtual IP. It is not a fourth control-plane node. External clients should use it instead of an individual control-plane VM address.

The three control-plane VMs use embedded etcd. Keep at least two of them online at all times so etcd retains quorum.

## 3. Fast path: run kubectl from a control-plane VM

Use this when you only need a few administrative commands or when the API VIP is unavailable. The bundled K3s kubectl already knows the local administrator configuration.

~~~sh
ControlUser=ubuntu
ControlPlane=10.0.0.110
SshKey=~/.ssh/id_rsa_control
ssh -i "$SshKey" "$ControlUser@$ControlPlane" 'sudo -n /usr/local/bin/k3s kubectl get nodes -o wide'
~~~

Other useful direct commands:

~~~sh
ssh -i "$SshKey" ubuntu@10.0.0.110 'sudo -n /usr/local/bin/k3s kubectl get pods -A'
ssh -i "$SshKey" ubuntu@10.0.0.111 'sudo -n /usr/local/bin/k3s kubectl -n monitoring get pods'
ssh -i "$SshKey" ubuntu@10.0.0.112 'sudo -n /usr/local/bin/k3s etcd-snapshot ls'
~~~

The K3s administrator kubeconfig is root-owned. The current `ubuntu` guest user has passwordless sudo, so `sudo -n` succeeds without an interactive prompt.

## 4. Workstation access

### 4.1 Install clients

Atlas currently runs Kubernetes v1.36.3+k3s1. Keep the workstation kubectl client within one minor version of the cluster. helm is used for the installed releases listed above.

On WSL/Titan the verified clients are:

~~~sh
# kubectl v1.36.3
curl -fsSLo /tmp/kubectl https://dl.k8s.io/release/v1.36.3/bin/linux/amd64/kubectl
install -m 0755 /tmp/kubectl ~/.local/bin/kubectl

# helm v3.16.1
curl -fsSLo /tmp/helm.tgz https://get.helm.sh/helm-v3.16.1-linux-amd64.tar.gz
tar -C /tmp -xzf /tmp/helm.tgz
install -m 0755 /tmp/linux-amd64/helm ~/.local/bin/helm
~~~

`~/.local/bin` is already on the WSL PATH, so both commands resolve directly. Older clients bundled with Docker Desktop (`kubectl.exe` v1.32.2) or the WindowsApps winget shim (v1.29.1) are more than one minor version behind and should not be relied on.

### 4.2 Test connectivity first

From WSL/Linux:

~~~sh
timeout 5 bash -c 'echo > /dev/tcp/10.0.0.108/6443' && echo "API VIP reachable"
timeout 5 bash -c 'echo > /dev/tcp/10.0.0.110/22'  && echo "cp1 SSH reachable"
~~~

From Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName 10.0.0.108 -Port 6443
Test-NetConnection -ComputerName 10.0.0.110 -Port 22
~~~

Both tests should succeed. If port 6443 fails, use the recovery path in section 7 before changing any kubeconfig.

### 4.3 Retrieve a separate Atlas administrator kubeconfig

K3s stores its built-in administrator kubeconfig on every control-plane VM at this path:

~~~text
/etc/rancher/k3s/k3s.yaml
~~~

That file normally has a local server address of https://127.0.0.1:6443. A copy used outside the VM must change only that server address to the VIP. Preserve the embedded certificate authority, client certificate, and client key exactly as copied.

Do not overwrite a pre-existing default kubeconfig. On Titan, `C:\Users\Dave\.kube\config` points to an unrelated local minikube endpoint, 127.0.0.1:57966.

From WSL/Linux, create a separate Atlas config:

~~~sh
mkdir -p ~/.kube
ssh -i ~/.ssh/id_rsa_control ubuntu@10.0.0.110 'sudo -n cat /etc/rancher/k3s/k3s.yaml' > ~/.kube/atlas-admin.yaml
sed -i 's|https://127.0.0.1:6443|https://10.0.0.108:6443|' ~/.kube/atlas-admin.yaml
chmod 600 ~/.kube/atlas-admin.yaml
kubectl --kubeconfig ~/.kube/atlas-admin.yaml config rename-context default atlas-admin
~~~

From Windows PowerShell:

~~~powershell
$ControlUser = 'ubuntu'
$BootstrapControlPlane = '10.0.0.110'
$ApiVip = '10.0.0.108'
$SshKey = Join-Path $env:USERPROFILE '.ssh\id_rsa_control'
$KubeDirectory = Join-Path $env:USERPROFILE '.kube'
$AtlasKubeconfig = Join-Path $KubeDirectory 'atlas-admin.yaml'

New-Item -ItemType Directory -Force -Path $KubeDirectory | Out-Null
ssh -i $SshKey "$ControlUser@$BootstrapControlPlane" 'sudo -n cat /etc/rancher/k3s/k3s.yaml' | Set-Content -LiteralPath $AtlasKubeconfig -Encoding ascii

$yaml = Get-Content -LiteralPath $AtlasKubeconfig -Raw
$yaml = $yaml -replace 'https://127\.0\.0\.1:6443', ('https://' + $ApiVip + ':6443')
Set-Content -LiteralPath $AtlasKubeconfig -Value $yaml -Encoding ascii -NoNewline

kubectl --kubeconfig $AtlasKubeconfig config rename-context default atlas-admin
~~~

The copied file grants cluster-admin access. Treat it like an administrative SSH private key.

### 4.4 Restrict the local file

The WSL copy is already mode `600`. On Windows:

~~~powershell
icacls $AtlasKubeconfig /inheritance:r
icacls $AtlasKubeconfig /grant:r "$($env:USERNAME):(R,W)" "Administrators:(R,W)"
~~~

Never commit this file, attach it to a ticket, send it in chat, or paste its embedded client-key-data anywhere.

### 4.5 Use the config

The safest habit is to name the config for each command:

~~~sh
kubectl --kubeconfig ~/.kube/atlas-admin.yaml get nodes -o wide
kubectl --kubeconfig ~/.kube/atlas-admin.yaml get pods -A
kubectl --kubeconfig ~/.kube/atlas-admin.yaml get --raw='/readyz?verbose'
~~~

For the current shell session:

~~~sh
export KUBECONFIG=~/.kube/atlas-admin.yaml
kubectl config current-context
kubectl cluster-info
kubectl get nodes -o wide
~~~

Optional convenience alias:

~~~sh
alias k='kubectl --kubeconfig ~/.kube/atlas-admin.yaml'
k get nodes
k -n monitoring get pods
~~~

Avoid setting Atlas as a permanent, machine-wide default until you have decided how to handle multiple clusters. A dedicated file reduces the risk of running an administrator command against the wrong cluster.

## 5. Validate that kubectl reached Atlas

Run these checks after creating or refreshing the config:

~~~sh
kubectl --kubeconfig ~/.kube/atlas-admin.yaml config view --minify
kubectl --kubeconfig ~/.kube/atlas-admin.yaml get nodes -o wide
kubectl --kubeconfig ~/.kube/atlas-admin.yaml get pods -A
kubectl --kubeconfig ~/.kube/atlas-admin.yaml -n monitoring get scrapeconfig
helm --kubeconfig ~/.kube/atlas-admin.yaml list -A
~~~

Expected nodes (verified 2026-10-02):

~~~text
NAME                STATUS   ROLES                AGE   VERSION        INTERNAL-IP   OS-IMAGE             CONTAINER-RUNTIME
atlas-k3s-cp1       Ready    control-plane,etcd   48d   v1.36.3+k3s1   10.0.0.110    Ubuntu 24.04.4 LTS   containerd://2.3.2-k3s2
atlas-k3s-cp2       Ready    control-plane,etcd   48d   v1.36.3+k3s1   10.0.0.111    Ubuntu 24.04.4 LTS   containerd://2.3.2-k3s2
atlas-k3s-cp3       Ready    control-plane,etcd   48d   v1.36.3+k3s1   10.0.0.112    Ubuntu 24.04.4 LTS   containerd://2.3.2-k3s2
atlas-k3s-worker1   Ready    worker               48d   v1.36.3+k3s1   10.0.0.113    Ubuntu 24.04.4 LTS   containerd://2.3.2-k3s2
~~~

Namespaces verified 2026-10-04 included `default`, `kube-node-lease`,
`kube-public`, `kube-system`, `argocd`, `cert-manager`, `gitea`, `sealed-secrets`,
`monitoring`, `demo`, `redop`, and an empty orphan `external-dns`. The `demo`
namespace is legacy: its workload is no longer declared in Git and the namespace
may remain until live Argo reconciliation removes owned resources.

The active cluster endpoint should be https://10.0.0.108:6443, never 127.0.0.1, when the command runs from Titan or WSL.

## 6. Proxmox root access

Proxmox root is for infrastructure and recovery. It can inspect or control VMs but does not replace Kubernetes RBAC.

### 6.1 Inspect PVE and VM state

~~~sh
PveHost=10.0.0.101
ssh root@$PveHost 'pvecm status; qm list'
ssh root@$PveHost 'qm status 201; qm config 201'
~~~

Host-to-VM mapping:

~~~text
Turing    10.0.0.101   VMID 201   atlas-k3s-cp1
Hopper    10.0.0.102   VMID 202   atlas-k3s-cp2
Lovelace  10.0.0.103   VMID 203   atlas-k3s-cp3
Babbage   10.0.0.104   VMID 204   atlas-k3s-worker1
~~~

PVE root is a password credential; it is not authorized by `~/.ssh/id_rsa_control`. Expect a password prompt rather than key-based login.

### 6.2 Prefer graceful VM operations

~~~sh
ssh root@10.0.0.101 'qm shutdown 201'
ssh root@10.0.0.101 'qm status 201'
ssh root@10.0.0.101 'qm start 201'
~~~

Avoid `qm stop` unless the guest is unresponsive; it is an abrupt power-off.

For VMIDs 201, 202, and 203, never deliberately take down more than one at a time. Validate recovery before doing further maintenance:

~~~sh
kubectl --kubeconfig ~/.kube/atlas-admin.yaml get nodes
ssh -i ~/.ssh/id_rsa_control ubuntu@10.0.0.110 'sudo -n /usr/local/bin/k3s etcd-snapshot ls'
~~~

### 6.3 Console recovery

If a serial console is configured, attempt:

~~~sh
ssh -t root@10.0.0.101 'qm terminal 201'
~~~

If no serial console exists, use the VM Console in the Proxmox web UI. Console access is a recovery tool, not the normal way to administer Kubernetes.

## 7. Failure and recovery paths

### The API VIP is unavailable

1. Confirm that the control-plane VMs are running:

   ~~~sh
   ssh root@10.0.0.101 'qm status 201'
   ssh root@10.0.0.102 'qm status 202'
   ssh root@10.0.0.103 'qm status 203'
   ~~~

2. SSH to any surviving control-plane VM and use its local K3s client:

   ~~~sh
   ssh -i ~/.ssh/id_rsa_control ubuntu@10.0.0.110 'sudo -n /usr/local/bin/k3s kubectl get nodes -o wide'
   ~~~

3. If cp1 is unavailable, use cp2 or cp3. Do not reset etcd, rebuild a control-plane node, or alter kube-vip just because one control-plane VM is down.

4. Restore service one control-plane VM at a time. When the VIP returns, repeat the validation in section 5.

### kubectl reports an x509 certificate error

Inspect the active configuration:

~~~sh
kubectl --kubeconfig ~/.kube/atlas-admin.yaml config view --minify
~~~

Ensure that the external configuration uses https://10.0.0.108:6443. Do not solve this by setting insecure-skip-tls-verify. Correct the endpoint or certificate configuration instead.

### kubectl times out or reports connection refused

- Confirm the API VIP is listening: `bash -c 'echo > /dev/tcp/10.0.0.108/6443'`.
- Check that at least two control-plane VMs are online.
- Use node-local kubectl through SSH to determine whether the Kubernetes API itself is healthy.
- Only after the local API works, inspect kube-vip:

  ~~~sh
  ssh -i ~/.ssh/id_rsa_control ubuntu@10.0.0.110 'sudo -n /usr/local/bin/k3s kubectl -n kube-system get pods -l app.kubernetes.io/name=kube-vip -o wide'
  ~~~

### The exported kubeconfig no longer authenticates

K3s renews inline certificates in its administrator kubeconfig as part of its lifecycle. A copied config is not updated automatically. Re-run section 4.3 from any healthy control-plane VM, then repeat section 5.

### SSH works but sudo fails

The VM template user lacks the required privilege. Correct the template or cloud-init policy so the guest user can run the required K3s administrator commands through sudo. On the current build `ubuntu` already has passwordless sudo. Do not make /etc/rancher/k3s/k3s.yaml world-readable.

## 8. Guardrails

- Use the VIP for workstation kubectl; use individual VM IPs for SSH and recovery only.
- Keep two embedded-etcd control-plane nodes healthy.
- Do not use the K3s node token as a kubectl credential. It joins nodes; it does not authorize Kubernetes administration.
- The K3s administrator kubeconfig is cluster-admin. Use scoped service accounts and restricted kubeconfigs for automation or non-administrator users.
- Keep Proxmox root access separate from day-to-day Kubernetes administration.
- Take and test etcd snapshots before control-plane upgrades or disruptive PVE maintenance.
- Rotate access material if a workstation containing an exported administrator kubeconfig is lost or compromised.

## 9. References

- [K3s cluster access](https://docs.k3s.io/cluster-access) - administrator kubeconfig location and the external endpoint replacement pattern.
- [K3s server options](https://docs.k3s.io/cli/server) - kubeconfig ownership and configuration options.
- [Install kubectl on Windows](https://kubernetes.io/docs/tasks/tools/install-kubectl-windows/) - Windows installation methods and client-version guidance.
