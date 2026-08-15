Exit code: 0
Wall time: 0.1 seconds
Output:
# Atlas Kubernetes control-plane access runbook

> Scope: Atlas is a four-host Proxmox cluster running a highly available K3s control plane. This is a tailored operational guide. It contains no passwords, private keys, node-join tokens, or kubeconfig credential data.

## Current deployed infrastructure

| Component | Status | Source-of-truth detail |
| --- | --- | --- |
| K3s | Deployed | v1.36.3+k3s1: three embedded-etcd control-plane VMs and one worker |
| Kubernetes API | Deployed | kube-vip virtual IP: https://10.0.0.108:6443 |
| Secret encryption | Deployed | Sealed Secrets encryption at rest |
| NFS CSI | Deployed | Driver is installed; no default StorageClass exists yet |
| TrueNAS | Pending storage configuration | TrueNAS is at 10.0.10.26. Create a dedicated dataset/export and configure credentials before provisioning Kubernetes volumes; do not reuse the existing movies export |
| Prometheus and Grafana | Deployed | kube-prometheus-stack runs in the monitoring namespace |
| Grafana access | Deployed | Network UI at http://10.0.0.110:3000 with anonymous Viewer access; administrator login remains available |
| K3s VM metrics | Deployed | Node Exporter DaemonSet runs across the K3s nodes |
| Physical PVE metrics | Deployed | Node Exporter runs on all four PVE hosts and Prometheus scrapes the atlas-proxmox-node-exporter job |
| Titan Windows metrics | Pending | Windows Exporter is not installed yet; the installation needs a one-time UAC approval |

## 1. Access model

Atlas has three separate administration layers. A credential for one layer does not automatically grant access to the next.

| Layer | Account or credential | What it administers |
| --- | --- | --- |
| Proxmox | root at a PVE host | Physical PVE host, VMs, storage, networks, and VM power state |
| Guest OS | control at a K3s VM | Ubuntu VM commands permitted through sudo |
| Kubernetes | Admin kubeconfig | Kubernetes resources, RBAC, workloads, and cluster settings |

This guide assumes:

- You can authenticate as root to the Proxmox hosts when needed.
- The VM template creates a control user with SSH access and sudo privileges.
- You have the appropriate SSH private key on the workstation.
- You are using Titan, currently 10.0.10.166, or another system that can reach the Atlas network.
- Passwords and keys are never stored in scripts, Git, shell history, tickets, or this document.

If an existing VM uses a different guest username, change only the ControlUser variable in the examples. Do not use Proxmox root as a Kubernetes credential.

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

~~~powershell
$ControlUser = 'control'
$ControlPlane = '10.0.0.110'
$SshKey = Join-Path $env:USERPROFILE '.ssh\id_rsa_control'
ssh -i $SshKey "$ControlUser@$ControlPlane" 'sudo /usr/local/bin/k3s kubectl get nodes -o wide'
~~~

Other useful direct commands:

~~~powershell
ssh -i $SshKey "$ControlUser@10.0.0.110" 'sudo /usr/local/bin/k3s kubectl get pods -A'
ssh -i $SshKey "$ControlUser@10.0.0.111" 'sudo /usr/local/bin/k3s kubectl -n monitoring get pods'
ssh -i $SshKey "$ControlUser@10.0.0.112" 'sudo /usr/local/bin/k3s etcd-snapshot ls'
~~~

The K3s administrator kubeconfig is root-owned. If control does not have passwordless sudo, SSH will request that account's sudo password.

## 4. Configure kubectl on Titan or another Windows workstation

### 4.1 Check the client version

Atlas currently runs Kubernetes v1.36.3+k3s1. Keep the workstation kubectl client within one minor version of the cluster.

~~~powershell
kubectl version --client --output=yaml
Get-Command kubectl
~~~

Titan currently has a kubectl executable supplied by Docker Desktop. If it is absent or not compatible, install a current Windows client:

~~~powershell
winget install -e --id Kubernetes.kubectl
kubectl version --client
~~~

### 4.2 Test connectivity first

~~~powershell
Test-NetConnection -ComputerName 10.0.0.108 -Port 6443
Test-NetConnection -ComputerName 10.0.0.110 -Port 22
~~~

Both tests should return TcpTestSucceeded: True. If port 6443 fails, use the recovery path in section 7 before changing any kubeconfig.

### 4.3 Retrieve a separate Atlas administrator kubeconfig

K3s stores its built-in administrator kubeconfig on every control-plane VM at this path:

~~~text
/etc/rancher/k3s/k3s.yaml
~~~

That file normally has a local server address of https://127.0.0.1:6443. A copy used outside the VM must change only that server address to the VIP. Preserve the embedded certificate authority, client certificate, and client key exactly as copied.

Do not overwrite a pre-existing default kubeconfig. On Titan, the current default path below points to an unrelated local endpoint, 127.0.0.1:57966:

~~~text
C:\Users\Dave\.kube\config
~~~

Create a separate Atlas config instead:

~~~powershell
$ControlUser = 'control'
$BootstrapControlPlane = '10.0.0.110'
$ApiVip = '10.0.0.108'
$SshKey = Join-Path $env:USERPROFILE '.ssh\id_rsa_control'
$KubeDirectory = Join-Path $env:USERPROFILE '.kube'
$AtlasKubeconfig = Join-Path $KubeDirectory 'atlas-admin.yaml'

New-Item -ItemType Directory -Force -Path $KubeDirectory | Out-Null
ssh -i $SshKey "$ControlUser@$BootstrapControlPlane" 'sudo cat /etc/rancher/k3s/k3s.yaml' | Set-Content -LiteralPath $AtlasKubeconfig -Encoding ascii

$yaml = Get-Content -LiteralPath $AtlasKubeconfig -Raw
$yaml = $yaml -replace 'https://127\.0\.0\.1:6443', ('https://' + $ApiVip + ':6443')
Set-Content -LiteralPath $AtlasKubeconfig -Value $yaml -Encoding ascii -NoNewline

kubectl --kubeconfig $AtlasKubeconfig config rename-context default atlas-admin
~~~

The copied file grants cluster-admin access. Treat it like an administrative SSH private key.

### 4.4 Restrict the local file

~~~powershell
icacls $AtlasKubeconfig /inheritance:r
icacls $AtlasKubeconfig /grant:r "$($env:USERNAME):(R,W)" "Administrators:(R,W)"
~~~

Never commit this file, attach it to a ticket, send it in chat, or paste its embedded client-key-data anywhere.

### 4.5 Use the config

The safest habit is to name the config for each command:

~~~powershell
kubectl --kubeconfig $AtlasKubeconfig get nodes -o wide
kubectl --kubeconfig $AtlasKubeconfig get pods -A
kubectl --kubeconfig $AtlasKubeconfig get --raw='/readyz?verbose'
~~~

For the current PowerShell session:

~~~powershell
$env:KUBECONFIG = $AtlasKubeconfig
kubectl config current-context
kubectl cluster-info
kubectl get nodes -o wide
~~~

Optional convenience function:

~~~powershell
function k {
  & kubectl --kubeconfig $AtlasKubeconfig @args
}

k get nodes
k -n monitoring get pods
~~~

Avoid setting Atlas as a permanent, machine-wide default until you have decided how to handle multiple clusters. A dedicated file reduces the risk of running an administrator command against the wrong cluster.

## 5. Validate that kubectl reached Atlas

Run these checks after creating or refreshing the config:

~~~powershell
kubectl --kubeconfig $AtlasKubeconfig config view --minify
kubectl --kubeconfig $AtlasKubeconfig get nodes -o wide
kubectl --kubeconfig $AtlasKubeconfig get pods -A
kubectl --kubeconfig $AtlasKubeconfig -n monitoring get scrapeconfig
~~~

Expected nodes:

~~~text
atlas-k3s-cp1       Ready   control-plane,etcd   10.0.0.110
atlas-k3s-cp2       Ready   control-plane,etcd   10.0.0.111
atlas-k3s-cp3       Ready   control-plane,etcd   10.0.0.112
atlas-k3s-worker1   Ready                       10.0.0.113
~~~

The active cluster endpoint should be https://10.0.0.108:6443, never 127.0.0.1, when the command runs from Titan.

## 6. Proxmox root access

Proxmox root is for infrastructure and recovery. It can inspect or control VMs but does not replace Kubernetes RBAC.

### 6.1 Inspect PVE and VM state

~~~powershell
$PveHost = '10.0.0.101'
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

### 6.2 Prefer graceful VM operations

~~~powershell
ssh root@10.0.0.101 'qm shutdown 201'
ssh root@10.0.0.101 'qm status 201'
ssh root@10.0.0.101 'qm start 201'
~~~

Avoid qm stop unless the guest is unresponsive; it is an abrupt power-off.

For VMIDs 201, 202, and 203, never deliberately take down more than one at a time. Validate recovery before doing further maintenance:

~~~powershell
kubectl --kubeconfig $AtlasKubeconfig get nodes
ssh -i $SshKey "$ControlUser@10.0.0.110" 'sudo /usr/local/bin/k3s etcd-snapshot ls'
~~~

### 6.3 Console recovery

If a serial console is configured, attempt:

~~~powershell
ssh -t root@10.0.0.101 'qm terminal 201'
~~~

If no serial console exists, use the VM Console in the Proxmox web UI. Console access is a recovery tool, not the normal way to administer Kubernetes.

## 7. Failure and recovery paths

### The API VIP is unavailable

1. Confirm that the control-plane VMs are running:

   ~~~powershell
   ssh root@10.0.0.101 'qm status 201'
   ssh root@10.0.0.102 'qm status 202'
   ssh root@10.0.0.103 'qm status 203'
   ~~~

2. SSH to any surviving control-plane VM and use its local K3s client:

   ~~~powershell
   ssh -i $SshKey "$ControlUser@10.0.0.110" 'sudo /usr/local/bin/k3s kubectl get nodes -o wide'
   ~~~

3. If cp1 is unavailable, use cp2 or cp3. Do not reset etcd, rebuild a control-plane node, or alter kube-vip just because one control-plane VM is down.

4. Restore service one control-plane VM at a time. When the VIP returns, repeat the validation in section 5.

### kubectl reports an x509 certificate error

Inspect the active configuration:

~~~powershell
kubectl --kubeconfig $AtlasKubeconfig config view --minify
~~~

Ensure that the external configuration uses https://10.0.0.108:6443. Do not solve this by setting insecure-skip-tls-verify. Correct the endpoint or certificate configuration instead.

### kubectl times out or reports connection refused

- Run Test-NetConnection 10.0.0.108 -Port 6443.
- Check that at least two control-plane VMs are online.
- Use node-local kubectl through SSH to determine whether the Kubernetes API itself is healthy.
- Only after the local API works, inspect kube-vip:

  ~~~powershell
  ssh -i $SshKey "$ControlUser@10.0.0.110" 'sudo /usr/local/bin/k3s kubectl -n kube-system get pods -l app.kubernetes.io/name=kube-vip -o wide'
  ~~~

### The exported kubeconfig no longer authenticates

K3s renews inline certificates in its administrator kubeconfig as part of its lifecycle. A copied config is not updated automatically. Re-run section 4.3 from any healthy control-plane VM, then repeat section 5.

### SSH works but sudo fails for control

The VM template user lacks the required privilege. Correct the template or cloud-init policy so control can run the required K3s administrator commands through sudo. Do not make /etc/rancher/k3s/k3s.yaml world-readable.

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
