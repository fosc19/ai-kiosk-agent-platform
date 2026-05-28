# AI Kiosk Trace Viewer

Visualizador web de trazas con Gantt/Waterfall charts para análisis de latencias.

## Características

- 📊 **Waterfall Charts** - Visualización de eventos por turno conversacional
- 🔴 **Detección de Violaciones SLA** - Highlighting automático de latencias excesivas
- 🔄 **Auto-refresh** - Actualización automática cada 5 segundos
- 📈 **Métricas detalladas** - Latencias por componente (ASR, LLM, TTS, etc.)
- 🎨 **Colores por servicio** - Fácil identificación visual

## Requisitos

- Node.js 18+
- pnpm
- Trace Collector corriendo en puerto 9002

## Instalación

```bash
cd apps/trace-viewer
pnpm install
```

## Uso

### 1. Arrancar el Trace Collector

Desde el root del proyecto:

```bash
task trace:collector
```

El collector debe estar corriendo en `http://localhost:9002`.

### 2. Arrancar el Viewer

```bash
pnpm dev
```

El viewer estará disponible en `http://localhost:9003`.

### 3. Generar Trazas

Ejecuta una sesión o un Golden Flow para generar trazas:

```bash
# Opción 1: Sesión manual
task dev:ui-kiosk

# Opción 2: Golden Flow
task trace:golden FLOW=navigation/store_location.yml
```

### 4. Visualizar

Abre el navegador en `http://localhost:9003` y selecciona una traza de la lista.

## Estructura del Proyecto

```
apps/trace-viewer/
├── src/
│   ├── lib/
│   │   ├── types.ts              # Tipos TypeScript
│   │   ├── api.ts                # Cliente para Trace Collector
│   │   ├── waterfall-utils.ts    # Utilidades de conversión
│   │   ├── WaterfallChart.svelte # Componente principal de visualización
│   │   └── TraceList.svelte      # Lista de trazas disponibles
│   ├── routes/
│   │   ├── TraceListPage.svelte  # Página de lista
│   │   └── TraceDetailPage.svelte# Página de detalle con waterfall
│   ├── App.svelte                # App principal
│   ├── main.ts                   # Entry point
│   └── vite-env.d.ts             # Tipos de entorno
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
└── README.md
```

## Configuración

Crea un archivo `.env` (opcional):

```bash
cp .env.example .env
```

Variables disponibles:

```env
VITE_TRACE_COLLECTOR_URL=http://localhost:9002
```

## Interpretación del Waterfall

### Colores

- 🔵 **Azul** - Orchestrator
- 🟢 **Verde** - MCP Tools
- 🟡 **Amarillo** - Speech ASR (transcripción)
- 🟠 **Naranja** - Speech TTS (síntesis)
- 🔴 **Rojo** - Violación de SLA

### SLA Thresholds

| Componente | Límite |
|-----------|--------|
| Turn total | 3000ms |
| ASR | 500ms |
| LLM first token | 800ms |
| TTS first chunk | 500ms |
| Classify | 150ms |
| Tool call | 100ms |

### Ejemplo de Lectura

```
Turn turn_001 (Total: 2345ms)
  VAD End        ▓▓░░░░░░░░  50ms   ✅
  ASR           ░░▓▓▓▓▓▓░░ 420ms   ✅
  Classify      ░░░░░░░░▓▓  80ms   ✅
  Tool: resolve ░░░░░░░░░░▓  30ms   ✅
  LLM Response  ░░░░░░░░░░▓▓▓▓ 650ms ✅
  TTS First     ░░░░░░░░░░░░▓▓▓ 320ms ✅
```

**Interpretación:**
- El turno completó en 2.3s (dentro de SLA ✅)
- ASR tomó 420ms (dentro del límite de 500ms)
- No hay barras rojas = sin violaciones

## Troubleshooting

### "Cannot connect to Trace Collector"

**Solución:**
```bash
# Verificar que el collector está corriendo
curl http://localhost:9002/healthz

# Si no está corriendo, iniciarlo
task trace:collector
```

### "No traces found"

**Solución:**
- Asegúrate de haber ejecutado al menos una sesión o Golden Flow
- Verifica que las trazas se están guardando:
  ```bash
  ls -la data/traces/sessions/
  ```

### El viewer no carga

**Solución:**
```bash
# Reinstalar dependencias
rm -rf node_modules
pnpm install

# Reiniciar dev server
pnpm dev
```

## Desarrollo

### Build para producción

```bash
pnpm build
```

El output estará en `dist/`.

### Preview del build

```bash
pnpm preview
```

### Type checking

```bash
pnpm check
```

## Integración con Golden Flows

El viewer se integra perfectamente con los Golden Flows existentes:

```bash
# 1. Ejecutar un Golden Flow
task trace:golden FLOW=navigation/store_location.yml

# 2. El flow genera una traza con trace_id conocido

# 3. Visualizar en el viewer
# Abre http://localhost:9003 y busca el trace_id
```

## Roadmap

Ver [OBSERVABILITY_PLAN.md](../../docs/OBSERVABILITY_PLAN.md) para el roadmap completo:

- ✅ **Fase 1:** Waterfall Viewer MVP (actual)
- 🔜 **Fase 2:** Comparaciones, filtros, exports
- 🔜 **Fase 3:** Migración a OpenTelemetry
- 🔜 **Fase 4:** Grafana Stack completo

## Referencias

- [TRACING.md](../../docs/TRACING.md) - Sistema de trazas F8
- [OBSERVABILITY_PLAN.md](../../docs/OBSERVABILITY_PLAN.md) - Estrategia completa
- [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) - Arquitectura general
