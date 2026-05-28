# Runbook

## Start backend services

```bash
task dev:services
```

## Start kiosk UI

```bash
task dev:ui
```

## Inspect containers

```bash
docker ps
```

## Inspect logs

```bash
docker logs -f ai-kiosk-speech-dev
docker logs -f ai-kiosk-mcp-tools-dev
```

## Reset dev containers

```bash
docker compose -f infra/docker-compose.dev.yml down -v
```

This runbook is intentionally minimal for the public portfolio edition.
