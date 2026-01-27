# Traefik Reverse Proxy

Traefik v3.3 reverse proxy for jr4.in homelab with automatic SSL via Cloudflare DNS challenge.

## 🚀 Quick Start

### 1. Create your `.env` file

```bash
cp .env.example .env
```

Then edit `.env` with your Cloudflare credentials:
- `CF_API_EMAIL`: Your Cloudflare account email
- `CF_DNS_API_TOKEN`: API token with Zone:DNS:Edit permission
- `TRAEFIK_DASHBOARD_AUTH`: Basic auth for the dashboard

### 2. Generate dashboard password

```bash
# Install htpasswd if needed
sudo apt install apache2-utils

# Generate the hashed password
htpasswd -nB admin
# Enter your desired password, then copy the output to .env
```

### 3. Create the acme.json file with correct permissions

```bash
mkdir -p certs logs
touch certs/acme.json
chmod 600 certs/acme.json
```

### 4. Start Traefik

```bash
docker compose up -d
```

### 5. Access the Dashboard

Visit: https://traefik.jr4.in

---

## 📁 File Structure

```
traefik/
├── docker-compose.yaml     # Main compose file
├── .env                    # Your credentials (gitignored)
├── .env.example            # Example credentials
├── config/
│   ├── traefik.yaml        # Static configuration
│   └── dynamic/
│       ├── middlewares.yaml # Security, compression, rate limiting
│       └── services.yaml    # All your service routes
├── certs/
│   └── acme.json           # SSL certificates (auto-generated)
└── logs/
    ├── traefik.log         # Traefik logs
    └── access.log          # Access logs
```

---

## 🌐 Configured Subdomains

| Subdomain | Service | Container |
|-----------|---------|-----------|
| `home.jr4.in` / `glance.jr4.in` | Glance Dashboard | glance:8080 |
| `portainer.jr4.in` | Portainer | portainer:9000 |
| `jellyfin.jr4.in` / `media.jr4.in` | Jellyfin | jellyfin:8096 |
| `music.jr4.in` / `swing.jr4.in` | SwingMusic | swingmusic:1970 |
| `qbit.jr4.in` / `torrent.jr4.in` | qBittorrent | qbittorrent:8080 |
| `ai.jr4.in` / `chat.jr4.in` | Open WebUI | big-bear-open-webui:8080 |
| `git.jr4.in` / `gitea.jr4.in` | Gitea | gitea:3000 |
| `vidown.jr4.in` / `dl.jr4.in` | Vidown | vidown-frontend:3000 |
| `convert.jr4.in` / `anyconv.jr4.in` | AnyConverter | anyconv:3000 |
| `convertx.jr4.in` | ConvertX | convertx:3000 |
| `files.jr4.in` / `fm.jr4.in` | File Manager | filemanager-nginx:80 |
| `f1.jr4.in` / `f1api.jr4.in` | F1 API | f1_api:4463 |
| `traefik.jr4.in` | Traefik Dashboard | (internal) |

---

## ➕ Adding New Services

### Option 1: Using Docker Labels (Recommended)

Add these labels to any container in its `docker-compose.yaml`:

```yaml
services:
  myservice:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myservice.rule=Host(`myservice.jr4.in`)"
      - "traefik.http.routers.myservice.entrypoints=websecure"
      - "traefik.http.routers.myservice.tls=true"
      - "traefik.http.routers.myservice.tls.certresolver=cloudflare"
      - "traefik.http.services.myservice.loadbalancer.server.port=8080"
    networks:
      - traefik-net

networks:
  traefik-net:
    external: true
```

### Option 2: Using Dynamic Configuration

Add to `config/dynamic/services.yaml`:

```yaml
http:
  routers:
    myservice:
      rule: "Host(`myservice.jr4.in`)"
      entryPoints:
        - websecure
      service: myservice
      tls:
        certResolver: cloudflare
      middlewares:
        - default-chain

  services:
    myservice:
      loadBalancer:
        servers:
          - url: "http://container-name:port"
```

---

## 🔒 Security Features

- **Automatic HTTPS** with Let's Encrypt via Cloudflare DNS challenge
- **Wildcard certificate** for `*.jr4.in`
- **Security headers** (HSTS, XSS protection, content type sniffing prevention)
- **Rate limiting** available for public APIs
- **Dashboard authentication** with basic auth

---

## 🔧 Troubleshooting

### Check Traefik logs
```bash
docker logs traefik -f
```

### Check certificate status
```bash
cat certs/acme.json | jq '.cloudflare'
```

### Test SSL certificate
```bash
curl -vI https://your-subdomain.jr4.in 2>&1 | grep -A5 "Server certificate"
```

### Common Issues

1. **Certificate not issued**: Check Cloudflare API token permissions
2. **503 Service Unavailable**: Container not on the same network as Traefik
3. **404 Not Found**: Check the Host rule matches exactly

---

## 🔗 Integration with Cloudflare Tunnel

Traefik handles internal routing and SSL certificates. Your Cloudflare Tunnel can point to Traefik for external access:

```yaml
# In cloudflared config, point to Traefik instead of individual services
ingress:
  - hostname: "*.jr4.in"
    service: http://traefik:80
  - service: http_status:404
```

This gives you a single entry point for all services!
