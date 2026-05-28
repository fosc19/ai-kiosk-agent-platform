#!/bin/bash

# Script para arrancar el Trace Viewer y Collector
# Uso: ./scripts/start-trace-viewer.sh

set -e

echo "🚀 AI Kiosk Trace Viewer - Setup & Start"
echo "======================================"
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. Verificar e instalar dependencias del Trace Collector
echo "📦 Verificando dependencias del Trace Collector..."
cd services/trace-collector

if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment no encontrado. Creando...${NC}"
    poetry install
fi

# Verificar que las deps estén instaladas
if ! .venv/bin/python -c "import structlog" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Dependencias incompletas. Instalando...${NC}"
    poetry install
fi

cd ../..

# 2. Instalar dependencias del Trace Viewer
echo ""
echo "📦 Verificando dependencias del Trace Viewer..."
cd apps/trace-viewer

if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}⚠️  node_modules no encontrado. Instalando...${NC}"
    pnpm install
fi

cd ../..

# 3. Verificar conflictos de puerto
echo ""
echo "🔍 Verificando puertos..."

# Verificar si el puerto 9002 está ocupado
if lsof -i :9002 >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Puerto 9002 ocupado (probablemente mcp-tools)${NC}"
    echo "   Usando puerto 9004 para el Trace Collector"
    COLLECTOR_PORT=9004
else
    COLLECTOR_PORT=9002
fi

# Verificar si el puerto 9003 está ocupado
if lsof -i :9003 >/dev/null 2>&1; then
    echo -e "${RED}❌ Puerto 9003 ocupado. Por favor, libéralo primero:${NC}"
    echo "   lsof -i :9003  # Ver qué lo usa"
    echo "   kill -9 <PID>  # Matar el proceso"
    exit 1
fi

echo -e "${GREEN}✅ Puertos disponibles${NC}"

# 4. Arrancar servicios
echo ""
echo "🚀 Arrancando servicios..."
echo ""
echo -e "${GREEN}   Trace Collector: http://localhost:${COLLECTOR_PORT}${NC}"
echo -e "${GREEN}   Trace Viewer:    http://localhost:9003${NC}"
echo ""
echo "Presiona Ctrl+C para detener ambos servicios"
echo ""

# Trap para matar procesos al salir
trap 'echo ""; echo "🛑 Deteniendo servicios..."; kill $COLLECTOR_PID $VIEWER_PID 2>/dev/null; exit' INT TERM

# Arrancar Trace Collector en background
cd services/trace-collector
TRACE_COLLECTOR_PORT=$COLLECTOR_PORT .venv/bin/python src/collector/main.py &
COLLECTOR_PID=$!
cd ../..

# Esperar a que el collector arranque
sleep 2

# Verificar que el collector arrancó
if ! curl -s http://localhost:${COLLECTOR_PORT}/healthz >/dev/null 2>&1; then
    echo -e "${RED}❌ Error: Trace Collector no arrancó correctamente${NC}"
    kill $COLLECTOR_PID 2>/dev/null
    exit 1
fi

echo -e "${GREEN}✅ Trace Collector corriendo en puerto ${COLLECTOR_PORT}${NC}"

# Arrancar Trace Viewer en background
cd apps/trace-viewer

# Configurar URL del collector
export VITE_TRACE_COLLECTOR_URL="http://localhost:${COLLECTOR_PORT}"

pnpm dev &
VIEWER_PID=$!
cd ../..

# Esperar a que el viewer arranque
echo "⏳ Esperando a que el Trace Viewer arranque..."
sleep 5

echo ""
echo -e "${GREEN}✅ Servicios arrancados correctamente!${NC}"
echo ""
echo "📖 Recursos:"
echo "   - Trace Viewer:    http://localhost:9003"
echo "   - Trace Collector: http://localhost:${COLLECTOR_PORT}"
echo "   - Healthcheck:     http://localhost:${COLLECTOR_PORT}/healthz"
echo ""
echo "💡 Para generar trazas:"
echo "   - Ejecuta el sistema: task dev:vps && task dev:ui"
echo "   - O usa Golden Flows: task trace:golden"
echo ""
echo "📚 Ver QUICKSTART.md para más información"
echo ""

# Esperar indefinidamente
wait
