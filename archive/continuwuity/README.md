# Continuwuity (Matrix Homeserver)

## Setup

1. Copy `.env.example` to `.env` and set all values.
2. Ensure Traefik is running.
3. Start the service:
   ```bash
   docker compose -f archive/continuwuity/docker-compose.yaml up -d
   ```

## Notes

- Database backend is local RocksDB at `/DATA/AppData/continuwuity`.
- This setup is private by default (`CONTINUWUITY_ALLOW_FEDERATION=false`).
- Upload size is controlled by `CONTINUWUITY_MAX_REQUEST_SIZE` (bytes).
- `CONTINUWUITY_TURN_SECRET` must match `TURN_SHARED_SECRET` in `infra/coturn/.env`.
