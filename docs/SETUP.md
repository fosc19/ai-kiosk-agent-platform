# Setup

## Requirements

- Node.js 20+
- pnpm 8+
- Python 3.11+
- Docker 24+
- Go Task 3+

## Environment files

```bash
cp .env.example .env
cp apps/ui-kiosk/.env.example apps/ui-kiosk/.env
cp services/orchestrator/.env.example services/orchestrator/.env
cp services/mcp-tools/.env.example services/mcp-tools/.env
```

## Install frontend packages

```bash
pnpm install
```

## Start services

```bash
task dev:vps
```

## Start UI

```bash
task dev:ui
```

## Notes

External provider keys are optional and intentionally not included. Use local/mock modes for portfolio review, or configure your own API keys in local `.env` files.
