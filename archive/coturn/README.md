# Coturn (TURN for Matrix VoIP)

## Setup

1. Copy `.env.example` to `.env`.
2. Set `TURN_EXTERNAL_IP` to your server public IP.
3. Set `TURN_SHARED_SECRET` and use the exact same value in:
   `archive/continuwuity/.env` -> `CONTINUWUITY_TURN_SECRET`.
4. Start the service:
   ```bash
   docker compose -f infra/coturn/docker-compose.yaml up -d
   ```

## Required Network Rules

Forward and allow these ports to this host:

- `3478/tcp`
- `3478/udp`
- `49152-49200/udp`

## DNS

- Create a DNS-only record like `turn.jr4.in` pointing to your public IP.
- Keep `matrix.jr4.in` behind your current Traefik + Cloudflare tunnel flow.
