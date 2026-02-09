# Homelab Server

Single Source of Truth for a Docker-based homelab. This repository tracks infrastructure, applications, and operational docs to restore the server from scratch.

## Documentation

- **[Repository Guidelines](AGENTS.md)**
- **[Work Queue](TODO.md)**
- **Service READMEs**: Many services include their own `README.md` inside the service folder.

## Directory Layout

- **`infra/`**: Core infrastructure (Traefik, databases, Portainer, Cloudflared).
- **`dapps/`**: User-facing applications (Jellyfin, Glance, Vidown, etc.).
- **`devops/`**: Development tools (Gitea, runners, Renovate, GitLab).

## Quick Start

1. **Bootstrap a fresh server** with `install.sh` (see `AGENTS.md` for repo standards).
2. **Create `.env` files** for services that require secrets (copy from `.env.example` if present).
3. **Start core infrastructure** (Traefik first):
   ```bash
   docker compose -f infra/traefik/docker-compose.yml up -d
   ```
4. **Start a service** (example: Jellyfin):
   ```bash
   docker compose -f dapps/jellyfin/docker-compose.yml up -d
   ```

## Services Index

### Infrastructure

- **[Traefik](infra/traefik/)**: Reverse proxy and edge router.
- **[Cloudflared](infra/cloudflared/)**: Secure remote access tunnel.
- **[Portainer](infra/portainer/)**: Container management UI.
- **[Databases](infra/databases/)**: Shared MariaDB & Postgres.

### DApps

- **[AnyConverter](dapps/anyconverter/)**
- **[ConvertX](dapps/convertx/)**
- **[Excalidraw](dapps/excalidraw/)**
- **[Glance](dapps/glance/)**
- **[Homelab FileManager](dapps/homelab-filemgr/)**
- **[Jellyfin](dapps/jellyfin/)**
- **[OpenWebUI](dapps/openwebui/)**
- **[QBittorrent](dapps/qbittorrent/)**
- **[Steam Headless](dapps/steam-headless/)**
- **[SwingMusic](dapps/swingmusic/)**
- **[Vidown](dapps/vidown/)**

### DevOps & Tools

- **[Gitea](devops/gitea/)**
- **[Gitea Runner](devops/gitea-runner/)**
- **[GitLab](devops/gitlab/)**
- **[GitLab Runner](devops/gitlab-runner/)**
- **[Renovate](devops/renovate/)**

### Archived / Inactive

- **[Affine](archive/affine/)**
- **[Siyuan](archive/siyuan/)**
- **[Vikunja](archive/vikunja/)**

## Operations Cheatsheet

Start a service:
```bash
docker compose -f dapps/<service>/docker-compose.yml up -d
```

Stop a service:
```bash
docker compose -f dapps/<service>/docker-compose.yml down
```

Follow logs:
```bash
docker compose -f dapps/<service>/docker-compose.yml logs -f
```

Update a service:
```bash
docker compose -f dapps/<service>/docker-compose.yml pull
docker compose -f dapps/<service>/docker-compose.yml up -d
```

Validate a compose file:
```bash
docker compose -f dapps/<service>/docker-compose.yml config
```

## Data & Backups

Back up critical locations as defined in service compose files:

- **`/DATA/AppData`**: Application configs and state.
- **`/DATA/Media`**: Media library.
- **Volumes**: `mariadb_data`, `postgres_data`, `gitea_data`.

## Conventions

- Each service has its own `docker-compose.yml`.
- Use `env_file: .env` for secrets and never commit `.env` files.
- Register new web apps in `infra/traefik/config/dynamic/services.yaml`.
- Standard practices and checklists live in `AGENTS.md`.

