# Trace Viewer - Quick Start

Guía rápida para empezar a usar el Trace Viewer en 5 minutos.

## Paso 1: Arrancar el Trace Collector

Desde el root del proyecto:

```bash
task trace:collector
```

Verás algo como:
```
🚀 Trace Collector starting on http://localhost:9002
```

Mantén este proceso corriendo.

## Paso 2: Arrancar el Trace Viewer

En otra terminal:

```bash
task trace:viewer
```

O si prefieres arrancar ambos al mismo tiempo:

```bash
task trace:full
```

El viewer estará en `http://localhost:9003`

## Paso 3: Generar Trazas de Prueba

Para tener datos que visualizar, necesitas ejecutar el sistema y generar algunas sesiones.

### Opción A: Usando el sistema completo

```bash
# Terminal 1: VPS services
task dev:vps

# Terminal 2: UI
task dev:ui

# Interactúa con la UI para generar trazas
```

### Opción B: Usando un Golden Flow

```bash
# Ejecutar un test que genera trazas
task trace:golden FLOW=navigation/store_location.yml
```

## Paso 4: Visualizar

1. Abre `http://localhost:9003` en tu navegador
2. Verás la lista de trazas disponibles
3. Haz click en "View" para ver el waterfall de una traza específica

## Interpretando el Waterfall

```
Turn turn_001 (Total: 2345ms) ━━━━━━━━━━━━━━━━━━━━━
  ┌─────────────────────────────────────────────┐
  │ VAD End        ▓▓░  50ms   ✅              │
  │ ASR           ░░▓▓▓▓░ 420ms ✅              │
  │ Classify      ░░░░░░▓ 80ms  ✅              │
  │ Tool: resolve ░░░░░░░▓ 30ms ✅              │
  │ LLM Response  ░░░░░░░░▓▓▓▓ 650ms ✅         │
  │ TTS First     ░░░░░░░░░░░▓▓ 320ms ✅        │
  └─────────────────────────────────────────────┘
     0ms    500ms   1000ms   1500ms   2000ms
```

### Colores

- 🔵 Azul = Orchestrator
- 🟢 Verde = MCP Tools
- 🟡 Amarillo = ASR (transcripción)
- 🟠 Naranja = TTS (síntesis)
- 🔴 Rojo = Violación de SLA

### Barras Rojas = Problemas

Si ves barras rojas, significa que ese componente excedió el SLA:

- Turn total > 3000ms
- ASR > 500ms
- TTS first chunk > 500ms
- Classify > 150ms

## Troubleshooting

### "Cannot connect to Trace Collector"

```bash
# Verificar si está corriendo
curl http://localhost:9002/healthz

# Si no responde, arrancarlo
task trace:collector
```

### "No traces found"

Normal si es la primera vez. Genera trazas ejecutando:

```bash
# Opción rápida
task trace:golden

# O usa el sistema completo
task dev:vps
task dev:ui
# Interactúa con la UI
```

### Puerto 9003 ocupado

```bash
# Encontrar qué proceso lo usa
lsof -i :9003

# Matar el proceso
kill -9 <PID>

# O cambiar el puerto en vite.config.ts
```

## Comandos Útiles

```bash
# Ver solo el viewer
task trace:viewer

# Ver solo el collector
task trace:collector

# Ver ambos (recomendado)
task trace:full

# Verificar health
curl http://localhost:9002/healthz
curl http://localhost:9003

# Listar trazas via API
curl http://localhost:9002/traces | jq .

# Ver detalle de una traza
curl http://localhost:9002/traces/session_abc123 | jq .
```

## Próximos Pasos

1. **Integrar con CI/CD** - Captura trazas en tests automáticos
2. **Comparar Runs** - Ver diferencias entre versiones
3. **Golden Flow Regression** - Detectar degradación de performance
4. **Exportar Reportes** - PDFs con waterfalls para documentación

Ver [OBSERVABILITY_PLAN.md](../../docs/OBSERVABILITY_PLAN.md) para el roadmap completo.
