# atlas

Configuration management 211 Lab Proxmox cluster

## Resources

https://github.com/lae/ansible-role-proxmox/tree/develop

https://docs.ansible.com/ansible/latest/collections/community/proxmox/proxmox_cluster_module.html

https://github.com/sbarbett/pihole-ansible

## Background

| Name                            | What / Who                                                                                                                          | Why it matters                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Atlas**                       | A British supercomputer from the 1960s, developed by the University of Manchester, Ferranti, and Plessey. ([Wikipedia][1])          | It was one of the first machines to use virtual memory and strong support for multitasking/multiprogramming. It was extremely influential in early OS design. ([Wikipedia][1])                                                                                                                                                                             |
| **Titan (supercomputer, ORNL)** | A more recent U.S. supercomputer built by Cray Inc., operating from 2012 to 2019 at Oak Ridge National Laboratory. ([Wikipedia][2]) | Titan was notable for being among the first large supercomputers to use a hybrid architecture combining CPUs and GPUs. It pushed forward scientific simulation capability. ([OLCF][6])                                                                                                                                                                     |
| **Alan Turing**                 | English mathematician, logician and cryptanalyst (1912-1954). ([Wikipedia][3])                                                      | Often considered the father of theoretical computer science; he made foundational contributions (the Turing Machine model, the concept of algorithm/computation, breaking Enigma) which underlie modern computing. ([Wikipedia][3])                                                                                                                        |
| **Grace Hopper**                | American computer scientist and U.S. Navy Rear Admiral (1906-1992). ([Wikipedia][4])                                                | A pioneer in developing compilers and high-level programming. She also was instrumental in developing COBOL, promoted usability of programming, popularized the metaphor “debugging.” ([Wikipedia][4])                                                                                                                                                     |
| **Ada Lovelace**                | English mathematician and writer, 1815-1852. ([Wikipedia][5])                                                                       | Worked with Charles Babbage on his proposed Analytical Engine. She is often regarded as the first “computer programmer” because she wrote what is recognized as the first algorithm intended to be processed by a machine. She also had insight into how machines could go beyond number-calculations to more general symbolic processes. ([Wikipedia][5]) |
| **Charles Babbage**             | English mathematician, philosopher, inventor and mechanical engineer (1791-1871). ([Wikipedia][7])                                  | Designed the Difference Engine and proposed the Analytical Engine, which are considered precursors to modern computers. His ideas influenced Ada Lovelace and laid essential groundwork for the concept of programmable machines. ([Wikipedia][7])                                                                                                         |

[1]: https://en.wikipedia.org/wiki/Atlas_%28computer%29?utm_source=chatgpt.com "Atlas (computer)"
[2]: https://en.wikipedia.org/wiki/Titan_%28supercomputer%29?utm_source=chatgpt.com "Titan (supercomputer)"
[3]: https://en.wikipedia.org/wiki/Alan_Turing?utm_source=chatgpt.com "Alan Turing"
[4]: https://en.wikipedia.org/wiki/Grace_Hopper?utm_source=chatgpt.com "Grace Hopper"
[5]: https://en.wikipedia.org/wiki/Ada_Lovelace?utm_source=chatgpt.com "Ada Lovelace"
[6]: https://www.olcf.ornl.gov/olcf-resources/compute-systems/titan/?utm_source=chatgpt.com "Titan - Oak Ridge Leadership Computing Facility"
[7]: https://en.wikipedia.org/wiki/Charles_Babbage?utm_source=chatgpt.com "Charles Babbage"

## Current infrastructure

The deployed Kubernetes platform is documented in [Kubernetes control plane](docs/kubernetes-control-plane.md). That runbook is the source of truth for the HA K3s topology, API VIP, control-plane access, monitoring, storage status, and operational guardrails.

The self-hosted git forge (Gitea), build runner, and Argo CD delivery pipeline are documented in [GitOps platform](docs/gitops-platform.md). Helm values and Argo CD Applications live under `gitops/` and `helm/`.

The whole platform (compute, storage, networking, control, delivery) is mapped in [C4 architecture](docs/c4-architecture.md) with Context, Container, Component, and Deployment diagrams.

An opencode agent skill that onboards an application end to end (add the `atlas` git remote, build, tag, deploy) lives at [`.opencode/skills/atlas-deploy-app`](.opencode/skills/atlas-deploy-app/SKILL.md).

## Process

Start with each node fresh with the Proxmox ISO.

Set IP of nodes in the proxmox setup `10.0.0.10X`

Bootstrap the `control` user with root credentials first. This is the
one run that may ask for the root SSH password:

```sh
ANSIBLE_SSH_ARGS="-C -o ControlMaster=auto -o ControlPersist=60s -o BatchMode=no" \
ansible-playbook ansible/playbooks/bootstrap-control.yaml -u root -k
```

Default Ansible access uses `root` over SSH with password auth prompts.
Verify connectivity:

```sh
ansible all -m ping -o -k
```

Run the regular maintenance playbooks:

```sh
ansible-playbook ansible/playbooks/update_all_packages_latest.yaml
ansible-playbook ansible/playbooks/no_subscription.yaml
ansible-playbook ansible/playbooks/sync-atlas-dns.yaml
```

Used the UI to create a cluster and copied the join info to each node with UI

had to debug babbage it wasn't reporting stats

first standardized on host files then ran through restart of certs and daemons

```
pvecm updatecerts -f
systemctl restart pve-cluster
systemctl restart corosync
systemctl restart pvestatd pvedaemon pveproxy
systemctl status pvestatd
```

## Notes

### 2026-04-10

- For memex to be a critical host I needed to remove it from the cluster as a stand alone node. With this there isn't a wait for Quorem to auto-start the VMs hosted on there.

- Updated `control` user with passwordless login and using local ssh key `id_rsa_control`

## Docs

- [Kubernetes control plane](docs/kubernetes-control-plane.md) — deployed topology, kubeconfig access, monitoring, storage status, and recovery procedures
- [C4 architecture](docs/c4-architecture.md) — Context, Container, Component and Deployment diagrams for compute, storage, networking, control, and delivery
- [Dedicated Pi-hole DNS](docs/pihole-dns.md) — Ansible provisioning of a dedicated Pi-hole plus automatic Ingress-to-DNS registration (ExternalDNS / dnsweaver)
- [GitOps platform](docs/gitops-platform.md) — Gitea forge, container registry, Actions CI, Argo CD app-of-apps, image promotion, secrets, and storage
- [Control user bootstrap](ansible/docs/control-user.md)
- [Proxmox Ubuntu 22.04 cloud-init VMs](ansible/docs/proxmox-cloudinit-ubuntu.md)
- [SSH config from inventory](ansible/docs/ssh-config-from-inventory.md)
