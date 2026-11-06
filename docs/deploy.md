# Automated deployment

[.github/workflows/deploy.yml](../.github/workflows/deploy.yml) has two jobs:

Each workflow runs only for changes in its own folders:

| Workflow | Runs on a push to `main` when these change | Pull requests |
|---|---|---|
| `deploy.yml` (servers) | `server/**`, `.github/deploy/**`, the workflow | tests when `server/**`, `web/**` or the deploy files change |
| `pages.yml` (site) | `web/**`, `server/dashboard/data/**` (monster catalog), the workflow | none |

A change to docs, `re/` or `tools/` alone neither restarts the servers nor republishes the site.
**Actions → Deploy/Pages → Run workflow** runs either one by hand. If `test` is ever made a required
check in the `main` ruleset, a pull request that touches none of those paths will wait for it forever:
keep it optional, or add a job that always passes.

- **test**, on pull requests targeting `main` and pushes to `main` (paths above):
  - `gofmt`, `go vet`, and the NEX server's Go tests;
  - the SIL server's end-to-end test;
  - the statistics portal's backend tests (PostgreSQL service) and frontend checks/build;
  - validation of `docker-compose.yml`.
- **deploy**, only after a push to `main` (normally a pull request merge), and only if `test` passes:
  1. Builds the `server-nex` and `server-dashboard` images on GitHub, because building them on the VPS would take about 13 minutes.
  2. Copies it to the VPS along with the files in `server/`.
  3. Runs [.github/deploy/remote.sh](../.github/deploy/remote.sh).

`remote.sh` works in `/opt/dqmj3p`:
- Keeps the current image as `server-nex:previous`.
- Loads the new image.
- Overwrites the tracked files from `server/`.
- Recreates the containers.

`.env`, `server/data`, SpotPass files, and Docker volumes are left untouched. At the end, the script checks
that the services are running and SpotPass responds. If anything goes wrong, the job fails and GitHub reports it.

A deployment restarts `nex`, so online players lose their connection for a few seconds.

Deployment only updates files present in the repository: a file deleted from `server/` remains on the VPS
until it is removed manually.

## One-time setup

### 1. SSH key for GitHub

Create a dedicated key without a passphrase (GitHub must use it unattended), separate from your own key.
In a WSL terminal:

```bash
ssh-keygen -t ed25519 -N "" -C github-actions-deploy -f ~/.ssh/dqmj3p_github_deploy
```

Add it to the VPS with the `restrict` option, which disables interactive terminals and forwarding.
This command connects using your usual key (`~/.ssh/dqmj3p`, prompting for its passphrase). Run it as your
own local user, without `sudo`:

```bash
(printf 'restrict '; cat ~/.ssh/dqmj3p_github_deploy.pub) | ssh -i ~/.ssh/dqmj3p root@188.245.46.173 'cat >> /root/.ssh/authorized_keys'
```

Check that it works without your usual key or SSH agent:

```bash
ssh -o IdentitiesOnly=yes -o IdentityAgent=none -i ~/.ssh/dqmj3p_github_deploy root@188.245.46.173 'docker ps -q | wc -l'
```

It should print the number of containers: 5.

### 2. GitHub secrets

In the repository's **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Value | How to obtain it |
|---|---|---|
| `VPS_HOST` | `188.245.46.173` | The VPS's primary IP address |
| `VPS_SSH_KEY` | The full **private** key, including the `BEGIN` and `END` lines | Run `cat ~/.ssh/dqmj3p_github_deploy` in WSL. Paste it only into the secret field |
| `VPS_KNOWN_HOSTS` | The VPS's public host key line | `ssh-keyscan -t ed25519 188.245.46.173` |

`VPS_KNOWN_HOSTS` ensures GitHub connects only to your VPS, rather than a server impersonating it.

You can use the [GitHub CLI](https://cli.github.com) to avoid copying values manually:

```bash
gh secret set VPS_HOST --body 188.245.46.173
gh secret set VPS_SSH_KEY < ~/.ssh/dqmj3p_github_deploy
ssh-keyscan -t ed25519 188.245.46.173 | gh secret set VPS_KNOWN_HOSTS
```

The `deploy` job uses the `production` environment, which GitHub creates on its first run. Under
**Settings → Environments → production**, you can optionally require manual approval before each deployment.

### 3. Firewall

GitHub runners use changing IP addresses, so port 22 must be open to all addresses in the Hetzner Cloud
Firewall. SSH accepts keys only, and fail2ban blocks repeated failed attempts.

### 4. Protecting `main`

Under **Settings → Branches → Add branch ruleset** (or *Add rule*) for `main`, enable:

- **Require a pull request before merging**.
- **Require status checks to pass**, selecting the `test` check.
- **Block force pushes**.
- Optionally, **Require branches to be up to date before merging**.

This ensures changes reach `main` through a pull request with passing tests, and every merge triggers deployment.

### 5. First deployment

The first deployment starts when the pull request containing the workflow is merged into `main`. Its
branch must also contain all work already deployed on the VPS (`vps-public-test` at the time of writing);
otherwise, deployment would replace the server code with the older code from `main`.

## Manual operations

Restore the previous `nex` image:

```bash
ssh root@188.245.46.173 'cd /opt/dqmj3p/server && docker tag server-nex:previous server-nex:latest && docker compose up -d --no-build nex'
```

Run deployment again without a new commit: **Actions → Deploy → Run workflow** on the `main` branch.

View service logs with `docker compose logs -f nex` (or `sil`, `spotpass`, `nncs`) in `/opt/dqmj3p/server`.
