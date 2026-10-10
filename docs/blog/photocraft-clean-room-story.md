# The clean room: how Photoshop became PhotoCraft

*A story about reverse engineering without stealing, specs as the product, and
an AI crew that ships. Posted 2026-10-10.*

## A room you can't lie in

The clean room was invented as a legal instrument. In 1982, Compaq's engineers
wanted an IBM PC that could run the same software, and the only thing standing
between them and a lawsuit was discipline. One team read IBM's BIOS and wrote
down what it *did* — every interrupt, every quirk — in dry technical prose.
A second team, sworn to have never seen the original, implemented the machine
from those papers alone. What crossed the wall between the teams was never
code. It was description. The clone shipped, the lawyers stood down, and the
industry learned the trick: you can own behavior by writing it down honestly.

Wine kept Windows APIs alive that way. Samba did it to SMB. Every serious
format re-implementation since is a descendant of that room.

## What you may copy

Behavior, not code. PhotoCraft — the open-source image editor we just deployed
to this cluster — states its version of the rule in one paragraph of its
contributor guide:

> We studied Photoshop and other proprietary editors for *behaviour and look
> only*. Never copy their code, shaders, profiles or assets. Implement from
> public specs (Adobe PSD spec, ICC, ISO 32000 blend modes, papers) and
> observation.

That is the whole contract. Adobe publishes the PSD specification, so the
file format is fair game — read the spec, write a parser, no decompiler
required. The ICC consortium publishes color management. ISO 32000 defines the
blend modes. Observation fills the gaps the specs don't cover: what exactly
happens when you drag a layer onto a mask, how the histogram reacts, where the
marching ants march. The look is studied the way a portrait artist studies a
face — by looking, never by tracing.

## The original becomes the oracle

Here is the part that turns clean-room from a legal trick into an engineering
method. You may not read the original's code, but you may read its *output*.

The project keeps a corpus of real Photoshop-authored PSD files and treats
them as test oracles: open each one, render it, compare. If PhotoCraft's
compositor disagrees with Photoshop's rendering of Photoshop's own document,
that is a failing test with a pixel-level diff attached. The proprietary
software is never the source. It becomes the test suite.

This is the quiet inversion at the heart of the story: the clean room stops
being a wall that keeps engineers away from the original, and becomes a funnel
that pulls the original's *behavior* into the open, one oracle at a time.

## 627 menu items

Parity is measured, not asserted. A generator walks Photoshop's menu tree
against the live command registry and publishes the score. The current report
in the repository reads: **627 of 627 menu items live — 100%** — File 51 of
51, Layer 161 of 161, Filter 75 of 75. The roadmap is more honest than the
number suggests: a menu item can exist and still behave worse than the
original, and the docs say so. But the target is not "an editor like
Photoshop". It is 1:1 parity — same menus, same shortcuts, same behavior, same
file fidelity — rebuilt in pure Rust, with no `unsafe` outside one isolated
pen-tablet crate and a hard "never crash" rule that outranks feature work.

## Written for a crew of agents

Now the modern twist, and the reason this story belongs on this blog.

The repository's front door is not a README for humans. It is `AGENTS.md`:
a guide *for AI agents and contributors*, and it declares the goal plainly —
every feature must be drivable by agents. The architecture makes that more
than a slogan:

- **Everything is a command.** Each user-visible action is a registered
  command with an id, a menu path and a shortcut. The UI, the CLI, the control
  channel and the MCP server all dispatch the same command ids. There is no
  private path into the app.
- **The app is drivable.** The desktop build speaks JSON over a loopback TCP
  control channel with token authentication; agents open documents, run
  commands and screenshot the running app to check their work.
- **The truth is generated.** Parity reports and performance scorecards are
  produced by tooling from the live registry, not hand-written optimism.

This is what AI engineering actually is, when it is done seriously. Not
prompting harder — building the seams that make machine work *verifiable*:
command registries instead of screen scraping, oracles instead of vibes,
generated scorecards instead of demos. The agents are not a gimmick bolted
onto the project; they are the intended workforce, and the codebase is their
factory floor.

## Shipping day

And then the last mile, which happened here, today.

The web build of PhotoCraft is the same Rust compiled to WebAssembly and
served by nginx — no JavaScript framework, no webview shell. We put it on the
lab's k3s cluster through the GitOps pipeline: the fork landed in our Gitea
forge, CI built the image and pushed it to the private registry, CI then
promoted the release tag into the platform repository, and Argo CD synced the
chart into the cluster. An AI agent did the whole path — wrote the workflow,
authored the Helm chart, sealed the registry pull secret, tagged `v0.6.1` —
and when the pod sat stuck in `ImagePullBackOff`, it traced the failure to a
drifted `/etc/hosts` line on one control-plane node, fixed the node, and got
its 200 OK from `https://photocraft.atlas.lan`.

A clean-room reimplementation of Photoshop, delivered end to end by the kind
of crew it was written for.

## The moral

Clean rooms used to be about lawyers: keep the code out, keep the lawsuit out.
They still are — but the discipline has grown teeth. A clean room is only as
strong as the specification at its center, and specifications precise enough
for lawyers are now, it turns out, precise enough for machines. Photoshop
became PhotoCraft the way the BIOS became Compaq: someone wrote down what it
does, not what it is.

The difference is who reads the spec next.

---

*Sources: the PhotoCraft repository's own docs — `AGENTS.md` (clean-room rule,
agent-first goal), `docs/parity.md` (generated menu parity), 
`docs/control-protocol.md` (agent control channel), `docs/contributing.md` —
plus the deployment record in the Atlas GitOps platform
(`docs/gitops-platform.md`). Deployed to `photocraft.atlas.lan` on 2026-10-10.*
