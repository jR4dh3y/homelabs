# Homelab Server

A comprehensive Docker-based homelab setup with multiple decentralized applications (dApps), services, and infrastructure components.

## 📁 Project Structure

### dApps
Production-grade applications running on the homelab:

- **[anyconverter](dapps/anyconverter/)** - SvelteKit-based file conversion utility
- **[excalidraw](dapps/excalidraw/)** - Collaborative whiteboarding application
- **[glance](dapps/glance/)** - Dashboard and monitoring service with custom API support
- **[homelab-filemgr](dapps/homelab-filemgr/)** - Full-stack file manager with Go backend and Svelte frontend
- **[swingmusic](dapps/swingmusic/)** - Music streaming application
- **[vidown](dapps/vidown/)** - Video downloader with Python backend and SvelteKit frontend

### DevOps & Infrastructure
Backend infrastructure and container orchestration:

- **[devops/](devops/)** - Container orchestration and CI/CD configurations
  - `gitea/` - Self-hosted Git service
  - `gitea-runner/` - Gitea CI/CD runner
  - `gitlab/` - GitLab instance (optional)
  - `renovate/` - Automated dependency updates

- **[infra/](infra/)** - Infrastructure services
  - `cloudflared/` - Cloudflare tunnel for secure access
  - `databases/` - Database configurations
  - `portainer/` - Docker UI management
  - `traefik/` - Reverse proxy and load balancer

## 🚀 Getting Started

### Prerequisites
- Docker & Docker Compose
- Linux-based environment
- Minimum 2GB RAM for core services
- Open ports for services (configurable via Traefik)

### Quick Start

1. **Clone and navigate to the project:**
   ```bash
   cd /home/pico/server
   ```

2. **Review configurations:**
   - Check [TODO.md](TODO.md) for current tasks
   - Review individual service READMEs in each dApp folder

3. **Deploy services:**
   ```bash
   # Start all services with Docker Compose
   docker-compose up -d
   
   # Or start individual services
   cd dapps/homelab-filemgr && docker-compose up -d
   ```

## 📋 Key Services

| Service | Type | Purpose |
|---------|------|---------|
| File Manager | Full-stack | File browsing & management |
| Glance | Dashboard | System monitoring & info display |
| Any Converter | Utility | File format conversion |
| Music | Streaming | Audio library management |
| Whiteboard | Collaboration | Excalidraw diagrams |
| Video Download | Utility | Media downloading |
| Traefik | Reverse Proxy | Routing & SSL termination |
| Portainer | Management | Docker container UI |
| Cloudflared | Networking | Secure external access |

