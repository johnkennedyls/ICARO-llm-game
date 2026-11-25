# El Escape de Ícaro

> **Proyecto Final · Algoritmos Computacionales**  
> Fundación Universitaria de Popayán — 2026-2  
> *Videojuego de laberinto con agentes inteligentes autónomos*

---

## 🎮 Descripción

**El Escape de Ícaro** es un videojuego 2D de vista cenital donde el jugador controla a **Ícaro**, atrapado en una estación subterránea cuyo sistema de seguridad (ARGOS) ha perdido el control. El objetivo: **recolectar 3 tarjetas de acceso y alcanzar la compuerta de emergencia** antes de que se agote la energía o ARGOS lo capture.

El proyecto implementa una **arquitectura de agentes inteligentes** completa con:
- **Percepción** → **Memoria/Contexto** → **Planificación** → **Decisión** → **Ejecución** → **Evaluación**
- **Dijkstra** y **A*** sobre grafos ponderados dinámicos (misma heurística Manhattan admisible y consistente)
- **Predicción recursiva acotada** para interceptación táctica
- **Comunicación multiagente** (drones → ARGOS)
- **Panel de monitoreo en tiempo real** con comparación algorítmica
- **Banco de experimentos reproducible** para análisis de complejidad

---

## 🚀 Instalación Rápida

```bash
# Clonar y entrar
cd icaro

# Crear entorno virtual (recomendado)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

> **Nota**: Requiere Python 3.10+ y `pygame-ce` (incluido en requirements).

---

## ▶️ Ejecución

```bash
# Juego completo (pantalla de título)
python main.py

# Saltar título, semilla fija
python main.py --seed 42 --start

# Mapa personalizado + piloto automático
python main.py --cells 21 14 --start --autopilot

# Ver ayuda completa
python main.py --help
```

### Controles Principales

| Tecla | Acción |
|-------|--------|
| `WASD` / `↑↓←→` | Mover a Ícaro |
| `E` | Hackear terminal cercana (−5 energía) |
| `P` | Alternar piloto automático (IA) |
| `H` | **Hablar con Operador (LLM)** |
| `TAB` / `1–4` | Cambiar agente en panel de monitoreo |
| `F1` | Alternar **A*** ↔ **Dijkstra** |
| `F2` | Mostrar/ocultar rutas planificadas |
| `F3` | Activar/desactivar niebla de guerra |
| `F5` | **Prueba de aceptación**: bloquear corredor |
| `F6` | Alarma de demostración |
| `R` | Reiniciar (misma semilla) |
| `N` | Nueva semilla aleatoria |
| `F11` | Pantalla completa |
| `ESC` | Pausa / Menú / Salir |

---

## 🧠 Arquitectura de Agentes

```
┌─────────────────────────────────────────────────────────────┐
│                      ENTORNO (Game/Maze)                     │
└──────────────────────────┬──────────────────────────────────┘
                           │ Percepción (visión local, eventos)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    MEMORIA Y CONTEXTO                        │
│  • Mapas de calor (heatmaps) de avistamientos               │
│  • Cruces frecuentes memorizados                            │
│  • Historial de planes, bloqueos, reportes                  │
│  • Notas tácticas compartidas                               │
└──────────────────────────┬──────────────────────────────────┘
                           │ Planificación (Dijkstra / A*)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      DECISIÓN                                │
│  • Seleccionar objetivo (patrulla, investigación, caza,     │
│    interceptación, huida)                                   │
│  • Evaluar coste/beneficio de bloquear puertas              │
└──────────────────────────┬──────────────────────────────────┘
                           │ Ejecución (movimiento por baldosas)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     EVALUACIÓN                               │
│  • ¿Llegó al objetivo? ¿Ruta bloqueada? ¿Avistó al jugador? │
│  • Actualizar memoria → Replanificar si necesario           │
└─────────────────────────────────────────────────────────────┘
```

### Agentes Implementados

| Agente | Rol | Algoritmo | Características |
|--------|-----|-----------|-----------------|
| **Ícaro** (Jugador) | Superviviente | Control manual / **Piloto IA** (A*/Dijkstra + evasión) | Energía, tarjetas, hackeo terminales |
| **ARGOS** | Cazador autónomo | A*/Dijkstra + **Predicción recursiva** (profundidad 4) | Patrulla, investigación, caza, interceptación, **bloqueo de puertas**, memoria de cruces |
| **Dron-1/2** | Exploradores | A*/Dijkstra | Patrulla sectorial, reporte de avistamientos a ARGOS, comunicación multiagente |

---

## 📊 Panel de Monitoreo (Lado Derecho)

El panel muestra en **tiempo real** para el agente seleccionado:

- **Estado actual** y objetivo
- **Percepción** (qué ve / recuerda)
- **Memoria/Contexto** (estadísticas, mapas de calor)
- **Métricas de búsqueda**: coste, nodos expandidos, tiempo (ms), longitud de ruta
- **Comparativa Dijkstra vs A*** (mismo origen, destino, grafo, costos)
- **Bloque específico**: predicción recursiva (ARGOS), ruta de patrulla (Drones), decisión del piloto (Ícaro)
- **Registro de eventos** cronológico con categorías coloreadas

---

## 🧪 Experimentos Reproducibles

Ejecuta el banco de pruebas comparando **Dijkstra vs A*** en múltiples condiciones:

```bash
# Completo (5 semillas × 4 tamaños × 3 escenarios × 5 repeticiones × 2 algoritmos)
python -m icaro.experiments

# Rápido (2 repeticiones, 2 semillas, 3 tamaños)
python -m icaro.experiments --quick

# Personalizado
python -m icaro.experiments --reps 10 --seeds 7,21,42,99,123
```

**Salidas generadas en `docs/`**:
- `experimentos.csv` — Datos crudos (una fila por repetición/algoritmo)
- `experimentos.md` — Informe con tablas resumen, verificación de optimalidad, análisis

**Métricas capturadas**: coste óptimo, pasos, nodos expandidos/generados, pico de frontera, tiempo CPU, memoria pico (tracemalloc).

---

## 📁 Estructura del Proyecto

```
icaro/
├── main.py                 # Punto de entrada
├── requirements.txt        # pygame-ce>=2.5.8
├── README.md               # Este archivo
├── TODO_DEVELOPMENT.md     # Plan de desarrollo
├── icaro.txt               # Storyboard narrativo
├── guia.txt                # Guía del proyecto final
├── capturas/               # Capturas de desarrollo
├── docs/                   # Experimentos (generado)
├── logs/                   # Registros de partidas (generado)
├── tests/
│   └── test_icaro.py       # Suite de tests unitarios
└── icaro/
    ├── __init__.py
    ├── config.py           # Constantes de juego (balance, visuales, algoritmos)
    ├── app.py              # Aplicación Pygame (ventana, bucle, entrada)
    ├── game.py             # Estado de partida (simulación pura, sin Pygame)
    ├── maze.py             # Generación procedural (recursive backtracker + braiding)
    ├── graph.py            # Grafo ponderado implícito (GridGraph)
    ├── algorithms.py       # Dijkstra & A* (SearchResult con métricas)
    ├── planning.py         # Predicción recursiva acotada (interceptación)
    ├── agents.py           # Agentes: Player, Argos, Drone, PlayerBot
    ├── session_log.py      # Logging persistente a archivo
    ├── experiments.py      # Banco de experimentos reproducible
    └── render/
        ├── __init__.py     # Renderer = ScreensMixin + UIMixin + WorldMixin
        ├── base.py         # Utilidades de dibujo (fuentes, formas, niebla, geometría)
        ├── world.py        # Mundo: baldosas, agentes, rutas, efectos, niebla
        ├── ui.py           # HUD, panel de monitoreo, pie de página
        └── screens.py      # Pantallas: título, pausa, fin de partida
```

---

## ✅ Pruebas de Aceptación (Criterios del Proyecto)

| Requisito | Implementación | Verificación |
|-----------|----------------|--------------|
| **Dijkstra + A*** sobre mismo grafo | `algorithms.py` + `game.py` | Tests unitarios + panel en vivo |
| **Heurística admisible y consistente** | Manhattan en `algorithms.py` | `heuristic_is_consistent()` + tests |
| **Recursividad con caso base/límite** | `planning.py:predict_intercept()` | `depth=0` y `node_budget` acotados |
| **Análisis complejidad temporal/espacial** | Docstrings + `experiments.py` | Métricas reales vs teóricas |
| **Panel: estado, objetivo, ruta, algoritmo, coste, nodos, tiempo** | `render/ui.py` | Visible en juego (TAB/F1/F2) |
| **Prueba bloqueo corredor + alternativa** | `game.try_blockade()` + `F5` | `test_blockade_has_valid_more_expensive_alternative` |
| **Métricas reales, código reproducible, demo cambio comportamiento** | `experiments.py` + logs | `python -m icaro.experiments` |

---

## 🧪 Tests Unitarios

```bash
# Ejecutar todos los tests
python -m pytest tests/ -v

# O directamente
python tests/test_icaro.py -v
```

**Cobertura**: Algoritmos (optimalidad, heurística), Grafo (bloqueo, métricas), Laberinto (determinismo, jugabilidad), Predicción (límites), Juego (victoria/derrota, bloqueos, drones), Renderizado (todas las pantallas), Experimentos (reproducibilidad).

---

## 📝 Logging y Evidencias

Cada partida genera un log en `logs/partida_<timestamp>_semilla<N>.log` con:
- Eventos cronológicos (timestamp, agente, categoría, mensaje)
- Resumen final: tiempo, tarjetas, energía, alarmas, bloqueos, búsquedas
- Métricas agregadas Dijkstra vs A* (nodos, tiempo, memoria)
- Pruebas de aceptación ejecutadas (bloqueos verificados)

---

## ⚙️ Configuración Avanzada (`icaro/config.py`)

Todas las constantes de balance y visuales están centralizadas:
- **Dimensiones**: `WINDOW_W/H`, `MAZE_RECT`, `PANEL_RECT`
- **Jugador**: `ENERGY_MAX`, `PLAYER_STEP_TIME`, `PLAYER_VISION`, `CARD_COUNT`
- **ARGOS**: `ARGOS_STEP_TIME`, `ARGOS_VISION`, `ARGOS_MEMORY_TTL`, `PREDICTION_DEPTH`, `PREDICTION_BUDGET`
- **Drones**: `DRONE_COUNT`, `DRONE_STEP_TIME`, `DRONE_VISION`
- **Costos baldosas**: `FLOOR_COST`, `SENSOR_COST`, `HAZARD_COST`, `DOOR_COST`
- **Seguridad**: `SECURITY_MAX`, `SENSOR_SECURITY`, `ARGOS_SECURITY_PER_S`
- **Algoritmos**: `ALGO_ASTAR`, `ALGO_DIJKSTRA`

Modifica `config.py` para experimentar sin tocar la lógica.

---

## 🔬 Análisis de Complejidad (Resumen)

| Algoritmo | Tiempo (teórico) | Espacio (teórico) | Notas |
|-----------|------------------|-------------------|-------|
| **Dijkstra** | O((V + E) log V) | O(V) | Montículo binario, lista adyacencia implícita |
| **A*** | O((V + E) log V) peor caso | O(V) | Con h admisible/consistente: óptimo sin reaperturas |
| **Predicción recursiva** | O(b^d) acotado | O(d) pila | b≤4 (grilla), d=4 default, `node_budget=700` |

> **Resultados empíricos** (promedio 5 repeticiones, semillas 7,21,42,99,123):
> - A* reduce **40–70% nodos expandidos** vs Dijkstra según tamaño
> - Coste de ruta **idéntico** en 100% de casos (heurística consistente)
> - Ratio tiempo A*/Dijkstra ≈ **0.3–0.6×** (más rápido en mapas grandes)

Ver `docs/experimentos.md` tras ejecutar experimentos para análisis completo.

---

## 🤖 Integración LLM (Implementada)

El proyecto incluye arquitectura completa para **agentes impulsados por LLM**:

- **Operador de Seguridad** (`H`): Diálogos contextuales, pistas adaptativas, narrativa emergente
- **Analista Táctico** (auto): Sugiere bloqueos óptimos a ARGOS, coordina drones, analiza patrones globales
- **Validación estricta**: Acciones LLM verificadas contra reglas del juego (`LLMActionValidator`)
- **Separación de latencia**: LLM corre en async/asyncio, **nunca bloquea** bucle de simulación (60 FPS)
- **Proveedores**: OpenAI, Anthropic, Ollama (local), Mock (tests), extensible
- **Determinismo**: `temperature=0`, `seed` fija, caché de respuestas por hash de contexto
- **Configuración**: Variables de entorno (ver `.env.example`)

Ver `icaro/llm_agents.py` y `DOCS/llm_integration.md`.

---

## 📦 Requisitos

- **Python** ≥ 3.10
- **pygame-ce** ≥ 2.5.8 (incluido en `requirements.txt`)
- Opcional: `tracemalloc` (stdlib) para mediciones de memoria en experimentos

---

## 📄 Licencia

Proyecto académico — Fundación Universitaria de Popayán — Algoritmos Computacionales 2026-2.  
Uso educativo y de investigación permitido con atribución.

---

## 👥 Créditos

Desarrollado como proyecto final de **Aprendizaje Basado en Retos (ABR)**.  
Arquitectura, algoritmos y agentes: implementación original con asistencia de IA generativa (permitida por la guía del proyecto).

---

## 🔗 Enlaces Útiles

- [Guía del proyecto](guia.txt)
- [Storyboard narrativo](icaro.txt)
- [Plan de desarrollo](TODO_DEVELOPMENT.md)
- [Experimentos](docs/experimentos.md) *(generado tras ejecutar)*
- [Logs de partidas](logs/) *(generado tras jugar)*