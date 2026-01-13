#!/bin/bash

# Server Installation & Setup Script
# Based on SERVER_SETUP_GUIDE.md strategy

set -e # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting Server Setup...${NC}"

# 1. System Updates
echo -e "${GREEN}[1/5] Updating system packages...${NC}"
sudo apt-get update
sudo apt-get upgrade -y

# 2. Install Essential Tools
echo -e "${GREEN}[2/5] Installing essential tools...${NC}"
sudo apt-get install -y \
    curl \
    wget \
    git \
    htop \
    vim \
    nano \
    unzip \
    jq \
    build-essential \
    net-tools \
    ca-certificates \
    gnupg

# 3. Install Docker & Docker Compose
if ! command -v docker &> /dev/null; then
    echo -e "${GREEN}[3/5] Installing Docker...${NC}"
    
    # Add Docker's official GPG key:
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc

    # Add the repository to Apt sources:
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    echo "Docker installed successfully."
else
    echo "Docker already installed. Skipping..."
fi

# 4. Configure Docker Permissions
echo -e "${GREEN}[4/5] Configuring user permissions...${NC}"
if [ $(getent group docker) ]; then
    if ! groups $USER | grep &>/dev/null "\bdocker\b"; then
        echo "Adding $USER to docker group..."
        sudo usermod -aG docker $USER
        echo "LOGOUT REQUIRED: You will need to log out and back in for this to take effect."
    fi
fi
sudo systemctl enable docker
sudo systemctl start docker

# 5. Setup Project Directories (if needed)
# Ensure dapps, devops, infra exist as per README
# echo -e "${GREEN}[5/5] Checking project structure...${NC}"
# mkdir -p dapps devops infra

echo -e "${BLUE}------------------------------------------------${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${BLUE}------------------------------------------------${NC}"
echo "Next steps:"
echo "1. Log out and back in to apply Docker group changes."
echo "2. Review 'SERVER_SETUP_GUIDE.md' for config details."
echo "3. Run 'docker compose up -d' in specific service folders."
