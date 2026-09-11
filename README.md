# status

The status page for *people you know*, at https://pykapp.github.io/status/.
DESIGN.md §15 argues every decision; this file is what a person does once to
make it exist, because none of it can be committed: accounts and tokens are
the operator's.

## What this is

`generate.py` renders one HTML page and one Atom feed from two inputs: what
an external prober last saw, and what a human has posted as incidents. The
page is text and inline SVG, loads nothing from anywhere, and defaults to
*we can't currently confirm service health* when the prober has not been
heard from in twenty minutes. `test_generate.py` reads the rendered bytes and
holds all of that; CI runs it on every push.

`workflow.yml` is the GitHub Actions workflow the **status repository** runs
every ten minutes and on every incident: it asks the prober, reads the
incidents, renders, and deploys the result to GitHub Pages. The repository
you are reading publishes these three files into that one on every merge to
`main` that touches `status/` (`.github/workflows/status-page.yml`).

## Once, by hand

1. **The repository.** Create `pykapp/status` under the `pykapp` organization,
   public, empty. Settings → Pages → *Source: GitHub Actions*. Its address is
   then `https://pykapp.github.io/status/`, which is the one compiled into the
   app (`Links.STATUS`).
2. **The label.** Create an issue label named `incident`. An incident is an
   issue with that label: open it to post, close it to resolve, edit it to
   update. Anybody with write access to the repository can do that from a
   phone, through GitHub's own sign-in, which is §15's rule 5.
3. **The prober.** A Better Stack Uptime account (free plan: ten monitors,
   three-minute checks, four regions). Three HTTP monitors against the API's
   public address, each with regions `us, eu, as, au`:
   - `/health` — expect 200
   - `/ready` — expect 200
   - `/probe/blob` — *follow redirects*, expect 200, keyword `pyk-canary`
   The third is the honest one: the API signs a URL for a canary object and
   the prober fetches it from storage, over the public endpoint, the way a
   phone fetches a photo. Name them so the page reads well; the page prints
   the names.
4. **The token.** Better Stack → API tokens → *Team-based tokens*: an Uptime
   API token for the team that holds the three monitors. Better Stack has no
   read-only scope—a team token can also edit that team's monitors—so the
   team should hold nothing but these three, and the token lives in one
   place: `pykapp/status` → Settings → Secrets → Actions, `BETTERSTACK_TOKEN`.
   Nothing else is needed: the incidents are read with the workflow's own
   token.
5. **The publisher's token.** In *this* repository, the Actions secret
   `STATUS_PUSH_TOKEN`: a fine-grained personal access token scoped to
   `pykapp/status` with *Contents: write* and *Workflows: write* (the second
   because the publisher pushes a workflow file). The same shape as
   `PAGES_PUSH_TOKEN` for the policies.
6. **Alerts to a person.** In Better Stack, the on-call e-mail for the three
   monitors is the operator's. That is the page for an outage; the metrics
   alerts in `ops/alerts.yml` are the page for everything the prober cannot
   see from outside.

After the first publish, open `https://pykapp.github.io/status/`: it should
say *all good* with three probes listed. Then pause one monitor in Better
Stack and wait for the next render: *we can't currently confirm service
health*. Resume it: *all good*. That is the deadman's switch, watched once.

## What shares nothing with what

The independence audit §13 owed, in one table. Re-run it before launch and
whenever any host changes.

| The page touches | Provider | Shared with the API? | With R2? | With a domain of ours? |
|---|---|---|---|---|
| `pykapp.github.io/status/` (the bytes) | GitHub Pages, fronted by Fastly | no—the API is a container on a host that is not GitHub, Fastly or Azure | no—R2 is Cloudflare | there is no domain of ours; `github.io` is GitHub's zone (Route 53 and NS1) |
| The render job | GitHub Actions | no runtime dependency; the API runs whether or not Actions does | no | no |
| The prober | Better Stack Uptime | reaches the API from outside, holds no credential of the API's | reaches R2 the way a phone does, with a URL the API signed | no |
| The incidents and their e-mail | GitHub Issues and its notifications | no | no | no |
| The `pykapp` account | GitHub, free plan | it also holds the policy pages; it holds nothing the API needs to run | no | no |
| The operator's sign-in | GitHub's | not our identity provider; there is none | — | — |

The one constraint this places on the host that is not yet chosen
(`prod-infra-setup`): **the API may not run on Azure, GitHub or Fastly**, and
it already may not run on Cloudflare. Fly, Render on AWS or GCP, or a VPS all
qualify.
