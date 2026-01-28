# Agent Guidelines for this Repository (Infrastructure)

## 1. Project Overview & Philosophy
This repository serves as the **"Single Source of Truth"** for a homelab server setup. It replaces tools like CasaOS with a Git-managed, Docker-based infrastructure.
- **Goal**: Full system restoration from this repo + one script (`install.sh`).
- **Scope**: Docker orchestration, network configuration (Traefik), and system setup.
- **Exclusions**: Source code of custom apps (treated as black boxes/images), heavy data (media), and secrets (`.env`).

## 2. Directory Structure
```
server/
├── dapps/           # Decentralized/Dockerized Applications (one folder per service)
│   ├── vidown/      # Video downloader (SvelteKit + Python)
│   ├── anyconverter/# File converter (SvelteKit)
│   ├── glance/      # Dashboard with custom APIs
│   ├── jellyfin/    # Media server
│   └── ...
├── infra/           # Core infrastructure services
│   ├── traefik/     # Reverse proxy (routes all traffic)
│   ├── cloudflared/ # Cloudflare tunnel for external access
│   ├── databases/   # Shared MariaDB & PostgreSQL
│   └── portainer/   # Docker UI management
├── devops/          # CI/CD and maintenance tools
│   ├── gitea/       # Self-hosted Git
│   ├── gitea-runner/# CI runner
│   └── renovate/    # Dependency updates
└── install.sh       # Bootstrap script for fresh servers
```

## 3. Build, Lint & Verification Commands

### Docker Compose Validation
```bash
# Lint/validate compose file syntax (run from service directory)
docker compose config

# Validate with specific file
docker compose -f dapps/<app>/docker-compose.yml config
```

### Deployment Commands
```bash
# Deploy a single service
docker compose -f dapps/<app>/docker-compose.yml up -d

# Rebuild after code changes
docker compose -f dapps/<app>/docker-compose.yml up -d --build

# View logs
docker compose -f dapps/<app>/docker-compose.yml logs -f

# Stop service
docker compose -f dapps/<app>/docker-compose.yml down
```

### System Verification
```bash
# Check for port conflicts
docker ps --format "table {{.Names}}\t{{.Ports}}"

# Verify Traefik routing
curl -I http://<service>.jr4.in

# Check container health
docker inspect --format='{{.State.Health.Status}}' <container_name>

# Test network connectivity between containers
docker exec traefik ping <container_name>
```

### Traefik Updates (Required when adding new networks)
```bash
docker compose -f infra/traefik/docker-compose.yml up -d
```

## 4. Docker Compose Standards
*All services must use `docker-compose.yml` (or `.yaml`).*

### Service Definition
- **Isolation**: Each service gets its own directory (e.g., `dapps/new-service/`).
- **Container Name**: ALWAYS specify `container_name: <service_name>` for DNS resolution.
- **Restart Policy**: `restart: unless-stopped` is standard.
- **Secrets**: Use `env_file: .env`. NEVER commit credentials to git.
- **Healthchecks**: Include healthchecks for critical services (see examples in vidown, anyconverter).

### Networking Strategy
Traefik is the reverse proxy. All web apps join the `proxy` network.

**Method A: Proxy Network (Preferred)**
```yaml
services:
  myapp:
    container_name: myapp
    networks:
      - proxy

networks:
  proxy:
    external: true
```

**Method B: Host Ports (Legacy)**
```yaml
ports:
  - "8080:80"  # Then reference via host.docker.internal:8080 in Traefik
```

### Traefik Service Registration
1. Add router in `infra/traefik/config/dynamic/services.yaml`:
```yaml
http:
  routers:
    myapp:
      rule: "Host(`myapp.jr4.in`)"
      entryPoints:
        - web
      service: myapp
      middlewares:
        - default-chain

  services:
    myapp:
      loadBalancer:
        servers:
          - url: "http://myapp-container:3000"
```

### Storage & Volumes
- **Config**: Bind mounts relative to compose file: `- ./config:/config`
- **Data**: Absolute paths for heavy data: `/DATA/...`
- **Permissions**: Use `user: "1000:1000"` when needed.

## 5. Code Style & Conventions

### YAML Formatting
- Use 2-space indentation
- Quote string values containing special characters
- Use lowercase for keys
- Group related services with comment headers

### Environment Variables
- Create `.env.example` with documented placeholders for any service requiring secrets
- Use descriptive variable names with service prefix: `GITEA_DB_HOST`, `FM_RATE_LIMIT_RPS`
- Never commit `.env` files (already in `.gitignore`)

### Naming Conventions
- **Directories**: lowercase, hyphenated (`homelab-filemgr`)
- **Container names**: lowercase, hyphenated, match directory name
- **Networks**: lowercase, descriptive (`proxy`, `db_net`)
- **Volumes**: lowercase with underscores (`gitea_data`, `postgres_data`)

### Security Practices
- Add `security_opt: - no-new-privileges:true` to all containers
- Use read-only mounts where possible: `- ./config:/config:ro`
- Set resource limits on production services
- Prefer `expose` over `ports` for internal-only services

## 6. Adding a New Service Checklist
1. [ ] Create `<(dapps/devops/infra)>/<service>/docker-compose.yml`
2. [ ] Set `container_name` matching directory name
3. [ ] Add `restart: unless-stopped`
4. [ ] Join `proxy` network (external: true)
5. [ ] Add healthcheck if service supports it
6. [ ] Create `.env.example` if secrets are needed
7. [ ] Register router and service in `infra/traefik/config/dynamic/services.yaml`
8. [ ] Validate with `docker compose config`
9. [ ] Test with `docker compose up -d`
10. [ ] Verify routing: `curl -I http://<service>.jr4.in`

## 7. Common Patterns

### Multi-Container Service (Frontend + Backend)
See `dapps/vidown/` or `dapps/homelab-filemgr/` for examples with:
- Frontend (SvelteKit/Node)
- Backend (Python/Go)
- Shared network
- Health-dependent startup

### Service with Custom Build Context
```yaml
services:
  app:
    build:
      context: ./subfolder
      dockerfile: Dockerfile
    container_name: myapp
```

### Database-Dependent Service
Reference shared databases in `infra/databases/`:
- PostgreSQL: `postgres:5432`
- MariaDB: `mariadb:3306`

## 8. Troubleshooting

### Container won't start
```bash
docker compose logs <service>
docker inspect <container> | grep -A 10 State
```

### Network issues
```bash
docker network ls
docker network inspect proxy
```

### Traefik not routing
1. Check container is on `proxy` network
2. Verify `services.yaml` syntax
3. Check Traefik logs: `docker logs traefik`
4. Confirm DNS resolves to server

---
*Maintained for AI agents operating in this repository*
