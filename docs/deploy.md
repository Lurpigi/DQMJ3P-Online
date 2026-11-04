# Deploy automatico

[.github/workflows/deploy.yml](../.github/workflows/deploy.yml) ha due job:

- **test**, su ogni pull request verso `main` e su ogni push su `main`:
  - `gofmt`, `go vet` e i test Go del server NEX;
  - il test end-to-end del server SIL;
  - il controllo di `docker-compose.yml`.
- **deploy**, solo dopo un push su `main` (cioè dopo il merge di una pull request) e solo se `test` passa:
  1. costruisce l'immagine `server-nex` su GitHub, perché sul VPS ci metterebbe circa 13 minuti;
  2. la copia sul VPS insieme ai file di `server/`;
  3. esegue [.github/deploy/remote.sh](../.github/deploy/remote.sh).

`remote.sh` lavora in `/opt/dqmj3p`:
- tiene l'immagine in uso come `server-nex:previous`;
- carica quella nuova;
- sovrascrive i file di `server/` che sono nel repository;
- ricrea i container.

`.env`, `server/data`, i file SpotPass e i volumi Docker non vengono toccati. Alla fine controlla che i
servizi siano attivi e che SpotPass risponda. Se qualcosa non va, il job fallisce e GitHub lo segnala.

Un deploy riavvia `nex`, quindi chi sta giocando online perde la connessione per qualche secondo.

Il deploy aggiorna solo i file che esistono nel repository: un file cancellato da `server/` resta sul VPS
finché non lo si toglie a mano.

## Da preparare una volta

### 1. Chiave SSH per GitHub

Una chiave dedicata, senza passphrase (GitHub la deve usare da sola), diversa dalla tua. In un terminale WSL:

```bash
ssh-keygen -t ed25519 -N "" -C github-actions-deploy -f ~/.ssh/dqmj3p_github_deploy
```

Aggiungila al VPS con l'opzione `restrict`, che toglie terminale interattivo e inoltri. Il comando usa la
tua chiave di sempre, quindi l'agent SSH deve essere sbloccato:

```bash
(printf 'restrict '; cat ~/.ssh/dqmj3p_github_deploy.pub) | ssh root@188.245.46.173 'cat >> /root/.ssh/authorized_keys'
```

Prova che funzioni da sola:

```bash
ssh -o IdentitiesOnly=yes -o IdentityAgent=none -i ~/.ssh/dqmj3p_github_deploy root@188.245.46.173 'docker ps -q | wc -l'
```

Deve stampare il numero dei container, cioè 5.

### 2. Secret su GitHub

In **Settings → Secrets and variables → Actions → New repository secret** del repository:

| Nome | Valore | Come ottenerlo |
|---|---|---|
| `VPS_HOST` | `188.245.46.173` | L'IP principale del VPS |
| `VPS_SSH_KEY` | Tutto il contenuto della chiave **privata**, righe `BEGIN` e `END` comprese | `cat ~/.ssh/dqmj3p_github_deploy` in WSL. Incollala solo nel campo del secret |
| `VPS_KNOWN_HOSTS` | La riga della chiave pubblica del VPS | `ssh-keyscan -t ed25519 188.245.46.173` |

`VPS_KNOWN_HOSTS` fa sì che GitHub si colleghi solo al tuo VPS e non a uno che si spaccia per lui.

Con la [CLI di GitHub](https://cli.github.com) si può fare senza copiare a mano:

```bash
gh secret set VPS_HOST --body 188.245.46.173
gh secret set VPS_SSH_KEY < ~/.ssh/dqmj3p_github_deploy
ssh-keyscan -t ed25519 188.245.46.173 | gh secret set VPS_KNOWN_HOSTS
```

Il job `deploy` usa l'environment `production`, che GitHub crea al primo avvio. In **Settings → Environments
→ production** puoi chiedere un'approvazione manuale prima di ogni deploy, se la vuoi.

### 3. Firewall

I runner di GitHub hanno indirizzi che cambiano, quindi nel Cloud Firewall di Hetzner la porta 22 deve
essere aperta a tutti. SSH accetta solo chiavi e fail2ban blocca chi prova a indovinare.

### 4. Protezione di `main`

In **Settings → Branches → Add branch ruleset** (o *Add rule*) per `main`:

- **Require a pull request before merging**;
- **Require status checks to pass**, con il controllo `test`;
- **Block force pushes**;
- facoltativo: **Require branches to be up to date before merging**.

Così su `main` si arriva solo con una pull request i cui test passano, e ogni merge fa partire il deploy.

### 5. Primo deploy

Il primo deploy parte quando su `main` arriva il merge che contiene il workflow. Il branch che lo porta deve
contenere anche tutto il lavoro già sul VPS (oggi `vps-public-test`), altrimenti il deploy rimetterebbe sul
server il vecchio codice di `main`.

## Operazioni a mano

Tornare all'immagine precedente di `nex`:

```bash
ssh root@188.245.46.173 'cd /opt/dqmj3p/server && docker tag server-nex:previous server-nex:latest && docker compose up -d --no-build nex'
```

Rilanciare il deploy senza un nuovo commit: **Actions → Deploy → Run workflow** sul branch `main`.

Log dei servizi: `docker compose logs -f nex` (o `sil`, `spotpass`, `nncs`) in `/opt/dqmj3p/server`.
