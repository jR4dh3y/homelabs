# Homelab-as-Code: Server Configuration & Git Strategy

This guide summarizes the strategy for managing your Ubuntu server (laptop-server) using Git, replacing CasaOS, and integrating remote access.

## 1. Git Repository Strategy
The goal is to create a "Single Source of Truth." If your hardware fails, you should be able to restore everything by cloning this repo and running a single script.

### What to Include
- **Docker Configs**: All `docker-compose.yml` files.
- **App Configs**: YAML/JSON files for Glance, Jellyfin, etc.
- **System Tweaks**: Laptop lid sleep settings (`logind.conf`), Netplan network configs.
- **Dotfiles**: `.zshrc`, aliases, and shell themes.
- **Scripts**: Installation and maintenance scripts.

### What to Exclude (via `.gitignore`)
- **Secrets**: `.env` files, API keys, private SSH keys.
- **Data**: Media files (movies), downloads, and large databases.

---

## 2. Recommended Folder Structure
```text
my-server-config/
├── .gitignore               # Ignore secrets and large data
├── bootstrap.sh             # The "One-Click" installer script
├── apps/                    # Docker & Service configurations
│   ├── glance/
│   │   ├── docker-compose.yml
│   │   └── config/          # server.yml, glance.yml
│   ├── jellyfin/
│   └── ...
├── system/                  # OS & Hardware level settings
│   ├── logind/              # Lid sleep fix (logind.conf)
│   ├── network/             # Static IP (netplan)
│   └── tailscale/           # VPN setup scripts
└── dotfiles/                # Shell environment (.zshrc, .aliases)
```

---

## 3. Replacing CasaOS
To move toward a more professional and Git-friendly setup, you can "unbundle" CasaOS into specialized containers.

### The Alternatives
- **Dockge**: A lightweight, Git-friendly web interface for Docker Compose. It stores stacks as plain files on disk.
- **FileBrowser**: A fast, powerful web-based file explorer to replace the CasaOS file manager.
- **Portainer**: Use "Stacks" with Git integration to automatically deploy changes from your repository.
- **Cosmos Cloud**: A modern alternative that includes an App Store, File Manager, and a built-in Reverse Proxy with Authentication.

### Migration Path
1. **Extract**: Copy Compose files from CasaOS to your Git structure.
2. **Map Data**: Ensure your new containers point to the existing data folders (e.g., `/DATA/AppData`).
3. **Test**: Run apps via Dockge/Terminal while CasaOS is stopped.
4. **Cleanup**: Uninstall CasaOS once the independent setup is verified.

---

## 4. Remote Access (Tailscale)
Tailscale provides secure remote access without opening ports.

- **System Level**: Install on Ubuntu to use the laptop as an **Exit Node** or **Subnet Router**.
- **Automation**: Include the installation in `bootstrap.sh`, but keep the **Auth Key** out of Git (use environment variables).
- **Static Networking**: Tailscale IPs never change, making it perfect for a server that might move between networks.

---

## 5. The "Installer" (bootstrap.sh)
Your automation script should perform these steps:
1. Update system packages.
2. Install Docker, Zsh, and Tailscale.
3. Apply system configs (copy `logind.conf` and `netplan` files).
4. Symlink dotfiles to the home directory.
5. Pull and start Docker containers.
