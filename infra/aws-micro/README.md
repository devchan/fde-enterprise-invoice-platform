# AWS micro deployment (cheapest path)

Runs the whole platform on **one small EC2 box** with the frontend on S3 +
CloudFront. Targets **~$0–3/mo during the 12-month AWS Free Tier**, ~$8–12/mo
after. It is single-instance (no HA) — meant for demo / low-volume use.

## What runs where

| Piece | Where | RAM |
|---|---|---|
| backend + worker | containers on the EC2 box | ~740 MB cap |
| Postgres (pgvector) | container on the box | 300 MB cap |
| Redis (job queue) | container on the box | 128 MB cap |
| frontend (SPA) | S3 + CloudFront (static) | 0 (off-box) |
| invoice files | local EBS disk by default | — |
| AI extraction | OpenAI/Gemini API | usage-based |

A 3 GB swapfile absorbs spikes so this fits a 1 GB t3.micro. It's tight — if you
can spend ~$18/mo, a **t3.small (2 GB)** removes all memory pressure.

## Files

- `cloud-init.yaml` — EC2 user-data: swap, Docker, clone, pull, run on boot.
- `docker-compose.micro.yml` — lean stack for a **1 GB box** ($5 tier), memory-capped.
- `docker-compose.small.yml` — same stack tuned for a **2 GB box** ($12 tier), relaxed caps + bigger Postgres buffers.
- `.env.micro.example` — env template (shared by both).
- `frontend-deploy.sh` — build SPA + push to S3 (+ CloudFront steps).
- `docker-compose.caddy.yml` + `Caddyfile` — shared reverse proxy: **auto-HTTPS**
  for the API and **multi-app routing** on one box (see below).

### Choosing the box size

| Tier | Box | Compose file |
|---|---|---|
| ~$5/mo (1 GB) | t3.micro (free tier) | `docker-compose.micro.yml` |
| ~$12/mo (2 GB) | Lightsail 2 GB / t3.small | `docker-compose.small.yml` |

For the 2 GB box, change the compose filename in `cloud-init.yaml`'s systemd unit
(three `-f docker-compose.micro.yml` occurrences → `docker-compose.small.yml`).

## Deploy steps

1. **Push the backend image** to a registry the box can pull (ECR / GHCR / Docker Hub).

2. **Fill in `cloud-init.yaml`** — replace every `__PLACEHOLDER__`
   (`__REGISTRY__`, `__IMAGE_TAG__`, `__DB_PASSWORD__`, `__JWT_SECRET__`,
   `__CLOUDFRONT_DOMAIN__`, `__OPENAI_API_KEY__`, `__GIT_REPO_URL__`,
   `__REGISTRY_LOGIN_COMMAND__`).
   > For real secrets, prefer fetching from **SSM Parameter Store** at boot
   > (`aws ssm get-parameter --with-decryption ...`) via an instance role, instead
   > of hard-coding them in user-data. See the login note in the file.

3. **Launch the instance** (free-tier eligible):
   ```bash
   aws ec2 run-instances \
     --image-id <ubuntu-24.04-ami> \
     --instance-type t3.micro \
     --key-name <your-key> \
     --security-group-ids <sg-allowing-22-80-443-8000> \
     --user-data file://cloud-init.yaml
   ```
   Give it an **instance role** with ECR pull (and SSM read, if used).

4. **Deploy the frontend**:
   ```bash
   API_BASE_URL=http://<ec2-public-dns>:8000 BUCKET=<unique-name> ./frontend-deploy.sh
   ```
   Then create the CloudFront distribution as the script prints, and set the
   backend's `CORS_ALLOWED_ORIGINS` to the resulting `https://<id>.cloudfront.net`.

5. **Verify**: `curl http://<ec2-public-dns>:8000/health/ready` and open the
   CloudFront URL.

## Reverse proxy + HTTPS (Caddy)

`docker-compose.caddy.yml` runs a small Caddy container that terminates HTTPS
(auto Let's Encrypt certs) and routes by domain to app containers over a shared
`edge` Docker network. This replaces the plain-HTTP `:8000` exposure and lets one
box host multiple repos.

Prerequisites:
- DNS **A record** for `API_DOMAIN` → the box's public IP.
- Security group opens **80 and 443** to the internet.
- Set `API_DOMAIN` and `ACME_EMAIL` in `.env`.

The `cloud-init.yaml` systemd unit already creates the `edge` network and starts
Caddy. To run it manually:
```bash
docker network create edge                 # once
docker compose --env-file .env -f docker-compose.micro.yml up -d --wait
docker compose --env-file .env -f docker-compose.caddy.yml up -d
```
Certs live in the `caddy_data` volume — don't delete it or you'll re-issue on
every restart and can hit Let's Encrypt rate limits. Once Caddy fronts the API,
you can drop the backend's public `ports: ["8000:8000"]` mapping (Caddy reaches
it over `edge`); keep it only for direct debugging.

### Hosting more repos on the same box
1. In the other repo's compose, add the backend/web service to the external
   `edge` network with a unique alias (e.g. `app2-web`).
2. Add a site block to `Caddyfile`:
   ```
   app2.example.com {
       reverse_proxy app2-web:3000
   }
   ```
3. `docker compose -f docker-compose.caddy.yml restart` to reload routes.

Share the heavy services (one Postgres with multiple DBs, one Redis with separate
DB indexes) rather than a full stack per repo to keep RAM sane. A 2 GB box
comfortably fits this app + a couple of light apps; add another heavy stack and
step up to a 4 GB box (~$24/mo).

## Monthly cost (us-east-1)

| Item | Free tier (12 mo) | After |
|---|---|---|
| t3.micro (750 hrs) | $0 | ~$8 |
| 30 GB gp3 EBS | $0 | ~$2.4 |
| S3 + CloudFront (frontend + files) | $0 | ~$1 |
| Data transfer | $0 (100 GB) | ~$1 |
| **AWS total** | **~$0–3** | **~$10–12** |
| OpenAI/Gemini | usage-based (~$20–60 / 1,000 invoices) | same |

## Notes & limits

- **Single instance = no HA.** A reboot restarts everything (systemd handles it);
  an instance failure means downtime until you relaunch.
- **Back up Postgres** — data lives on the EBS volume. Enable EBS snapshots, or
  `pg_dump` on a cron to S3. Losing the volume loses all data.
- **HTTPS on the API**: this exposes the API on `:8000` over HTTP. For production,
  put the API behind Caddy/nginx with a Let's Encrypt cert, or an ALB (adds ~$18/mo).
- **Amazon Linux 2023** instead of Ubuntu: swap `usermod -aG docker ubuntu` →
  `ec2-user`, and the `get.docker.com` script still works.
- **Scaling up** is a config change, not a rewrite: move Postgres → RDS and Redis
  → ElastiCache (point `DATABASE_URL`/`REDIS_URL` at them, drop those two services
  from the compose file) to reach the Tier-2 managed setup.
