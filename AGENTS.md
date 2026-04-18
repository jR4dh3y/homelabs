# Agent Guidelines for this Repository (Infrastructure)

## 2. Directory Structure
```
server/
├── apps/           # Dockerized Applications (one folder per service)
├── infra/           # Core infrastructure services
├── devops/          # CI/CD and maintenance tools
└── install.sh       # Bootstrap script for fresh servers
```

## 3. Build, Lint & Verification Commands

### System Verification
```bash

# Verify Traefik routing
curl -I http://<service>.jr4.in

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
- **Isolation**: Each service gets its own directory (e.g., `apps/new-service/`).
- **Container Name**: ALWAYS specify `container_name: <service_name>` for DNS resolution.
- **Restart Policy**: `restart: unless-stopped` is standard.
- **Secrets**: Use `env_file: .env`. NEVER commit credentials to git.

### Networking Strategy
Traefik is the reverse proxy. All web apps join the `proxy` network.

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
1. [ ] Create `<(apps/devops/infra)>/<service>/docker-compose.yml`
2. [ ] Set `container_name` matching directory name
3. [ ] Add `restart: unless-stopped`
4. [ ] Join `proxy` network (external: true)
5. [ ] Create `.env.example` if secrets are needed
6. [ ] Register router and service in `infra/traefik/config/dynamic/services.yaml`
7. [ ] Validate with `docker compose config`
8. [ ] Test with `docker compose up -d`
9.  [ ] Verify routing: `curl -I http://<service>.jr4.in`

## 7. Archiving Service Folders
- If the user says to "put a folder in archive", interpret this as a lifecycle change, not only a file move.
- Required sequence:
  1. Stop the service with `docker compose down` from its current folder.
  2. Move the service directory into `archive/<service>/`.
  3. Do not restart the archived service unless the user explicitly asks.

---
*Maintained for AI agents operating in this repository*
