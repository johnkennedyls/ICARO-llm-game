# Arquitectura de Agentes — El Escape de Ícaro

## 1. Modelo de Agente Unificado

Todos los agentes autónomos siguen el ciclo **PERCEPCIÓN → MEMORIA → PLANIFICACIÓN → DECISIÓN → EJECUCIÓN → EVALUACIÓN**:

```
┌──────────────┐     ┌──────────────┐     ┌────────────────┐
│  ENTORNO     │────▶│  PERCEPCIÓN  │────▶│  MEMORIA/      │
│  (Game/Maze) │     │  (visión,    │     │  CONTEXTO      │
│              │     │   eventos)   │     │  (heatmaps,    │
└──────────────┘     └──────────────┘     │   historial)   │
                          ▲               └───────┬────────┘
                          │                       │
                          │              ┌────────▼────────┐
                          │              │  PLANIFICACIÓN  │
                          │              │  (Dijkstra/A*)  │
                          │              └────────┬────────┘
                          │                       │
                          │              ┌────────▼────────┐
                          └──────────────│   DECISIÓN      │
                                         │  (seleccionar   │
                                         │   objetivo,     │
                                         │   bloquear?)    │
                                         └────────┬────────┘
                                                  │
                                         ┌────────▼────────┐
                                         │   EJECUCIÓN     │
                                         │  (mover paso a  │
                                         │   paso)         │
                                         └────────┬────────┘
                                                  │
                                         ┌────────▼────────┐
                                         │   EVALUACIÓN    │
                                         │  (¿llegó? ¿blo- │
                                         │   queado? ¿vio? │
                                         └────────┬────────┘
                                                  │
                                                  ▼
                                         ┌────────────────┐
                                         │ ACTUALIZAR     │
                                         │ ENTORNO/MEMORIA│
                                         └────────────────┘
```

**Clave**: La **replanificación** ocurre ante cualquier cambio relevante (objetivo nuevo, ruta bloqueada, avistamiento, timer).

---

## 2. Agentes Implementados

### 2.1 ARGOS — Cazador Autónomo Principal

#### 2.1.1 Estados (Máquina de Estados)
| Estado | Descripción | Transiciones |
|--------|-------------|--------------|
| `PATRULLA` | Recorre 4 puntos fijos (muestreo farthest-point) | → `INVESTIGA` si memoria reciente; → `CAZA/INTERCEPTA` si ve jugador |
| `INVESTIGA` | Va a `last_seen` (última posición conocida, TTL 12s) | → `PATRULLA` si llega y pasa 2.2s sin rastro; → `CAZA` si ve jugador |
| `CAZA` | Persigue **directamente** a Ícaro (posición actual) | → `INTERCEPTA` si predicción sugiere otra baldosa; → `INVESTIGA` si pierde contacto |
| `INTERCEPTA` | Va a `prediction.target` (donde *estará* Ícaro) | → `CAZA` si target = posición actual; → `INVESTIGA` si pierde contacto |

#### 2.1.2 Percepción
```python
def sees_player(self, game) -> bool:
    # 1. Distancia ≤ ARGOS_VISION (8.5 baldosas)
    # 2. Line-of-sight (Bresenham) sin muros/puertas cerradas
    return manhattan(self.tile, player.tile) <= VISION and graph.line_of_sight(...)
```
- **Visión directa**: LOS + radio
- **Reportes drones**: `receive_report(sender, position)` → actualiza `last_seen`, `heat`, notas
- **Sensores**: `notify_sensor(position)` → peso 1 en heat (vs 2 de visión directa)

#### 2.1.3 Memoria y Contexto
| Estructura | Tipo | Propósito |
|------------|------|-----------|
| `heat` | `Counter[Coord]` | Frecuencia de avistamientos por baldosa (peso: visión=2, sensor=1, reporte=2, cruce=+1) |
| `crossings` | `set[Coord]` | Baldosas con grado ≥ 3 donde se vio a Ícaro (prioridad en predicción) |
| `last_seen` | `Coord \| None` | Última posición confirmada |
| `last_seen_at` | `float` | Timestamp para TTL (12s) |
| `notes` | `deque[str]` | Log textual reciente (max 8) para panel |
| `prediction` | `PredictionResult` | Resultado última `predict_intercept()` |

#### 2.1.4 Planificación
- **Cada `think()`** (intervalo variable 0.36–1.1s según estado):
  1. Actualiza percepción → decide estado + objetivo
  2. Si objetivo cambió / ruta bloqueada / timer → `plan_to(game, {target})`
  3. `plan_to` ejecuta **Dijkstra Y A***, elige según `game.algorithm` (F1)
  4. Registra métricas en `game.register_search()`

#### 2.1.5 Predicción Recursiva (Intercepción)
```python
# En think(), si ve al jugador:
self.prediction = predict_intercept(
    maze, self.tile, player.tile, player_objectives, self.heat
)
target = self.prediction.target or player.tile
```
- **Profundidad 4**, **presupuesto 700 nodos** (configurable)
- **Heurística de plausibilidad**: `dist_objetivo - 2×heat + 0.08×steps`
- **Selección final**: del top 33% plausibles, la que ARGOS alcanza **antes** (`manhattan(argos, leaf) - 0.55×player_steps`)

#### 2.1.6 Bloqueo de Corredores (Acción Táctica)
```python
# Condiciones: ve/recuerda jugador + lock_ready_at + security ≥ 12
result = game.try_blockade("ARGOS", by_argos=True)
```
- Busca puerta en ruta óptima de Ícaro que:
  1. No esté ocupada
  2. **Tenga ruta alternativa válida** (todos los objetivos alcanzables sin ella)
  3. Coste alternativa ≤ 4× original o +80 (evita bloqueos triviales)
- **Cooldown**: 15s base, reduce con seguridad alta

#### 2.1.7 Velocidad Adaptativa
```python
speed_factor = 1.0 + 0.30 * min(security, 100) / 100
interval = max(ARGOS_STEP_MIN, step_time / speed_factor)
```
- `ARGOS_STEP_TIME = 0.225s` base → `ARGOS_STEP_MIN = 0.176s` con seguridad máxima
- **Think timer** también acelera con seguridad: `THINK_TIME * (1 - 0.25 * security/100)`

---

### 2.2 Drones Exploradores (2 instancias)

#### 2.2.1 Comportamiento
- **Ruta fija**: 2 waypoints (puntos de patrulla opuestos)
- **Estado**: `PATRULLA` → `AVISTAMIENTO` (ve jugador) → `ALERTA` (reciente) → `PATRULLA`
- **Visión**: radio 6 + LOS (más limitado que ARGOS)
- **Reporte**: cada 4s si ve jugador → `game.drone_report()` → actualiza ARGOS

#### 2.2.2 Planificación
- `plan_to(game, {waypoint})` cada 1.15s o si ruta bloqueada
- Solo Dijkstra/A* hacia waypoint actual (sin predicción, sin bloqueo)

#### 2.2.3 Comunicación Multiagente
```
Drón ve a Ícaro
      │
      ▼
game.drone_report(drone, player.tile)
      │
      ├─▶ drone.reports += 1
      ├─▶ game.stats["drone_reports"] += 1
      ├─▶ game.security += DRONE_SECURITY (6)
      ├─▶ argos.receive_report(drone.name, position)
      │       ├─▶ argos.last_seen = position
      │       ├─▶ argos.last_seen_at = now
      │       ├─▶ argos.heat[position] += 2
      │       └─▶ argos.memory.notes.append(...)
      └─▶ argos.think_timer = min(think_timer, 0.04)  # Replanificación inmediata
```

---

### 2.3 PlayerBot — Piloto Automático de Ícaro

#### 2.3.1 Objetivo
- Si hay tarjetas → ir a la más cercana (selector Dijkstra multi-objetivo)
- Si no hay tarjetas → ir a salida

#### 2.3.2 Bias de Riesgo (Evasión)
```python
def _risk_bias(self, game) -> dict[Coord, float]:
    bias = {}
    # Penaliza radio 4 alrededor de ARGOS
    for dx, dy in radio_4:
        dist = abs(dx) + abs(dy)
        penalty = {0: 999, 1: 60, 2: 32, 3: 12, 4: 3}[dist]
        bias[argos_tile + (dx,dy)] = max(bias.get(...), penalty * scale)
    # Penaliza predicción de intercepción
    if argos.prediction and argos.prediction.target:
        for dx, dy in radio_1:
            bias[pred_target + (dx,dy)] = max(bias.get(...), 16)
    return bias
```
- **Escala**: 1.0 si ARGOS ve/recuerda reciente; 0.65 si no
- **Efecto**: A* evita zonas peligrosas → rutas más seguras pero potencialmente más largas

#### 2.3.3 Replanificación
Triggers: ruta bloqueada, objetivos cambiaron, sin plan, cada 2s (`next_replan_at()`)

---

### 2.4 Player — Jugador Humano
- Control: `attempt_player_move(direction)` desde `App._movement()`
- Energía: −0.85/s base, −4.0 al pisar vapor
- Hackeo terminal: `E` → −5 energía, desbloquea puertas, desactiva sensores 12s, revela ARGOS 8s

---

## 3. Memoria Compartida y Coordinación

### 3.1 Mapa de Calor Global (`Argos.heat`)
- **Fuentes**: visión directa (peso 2), sensores (1), reportes drones (2), cruces (+1 extra)
- **Uso**: predicción recursiva (plausibilidad), bias de riesgo (PlayerBot)
- **Persistencia**: solo durante partida (se reinicia cada juego)

### 3.2 Cruces Memorizados (`Argos.crossings`)
- Baldosas con `degree ≥ 3` donde se vio a Ícaro
- **Bonus en predicción**: `-2.0 * min(heat, 6)` en plausibilidad
- **Semántica**: "Ícaro pasa por aquí a menudo → probable ruta de escape"

### 3.3 Notas Tácticas (`AgentMemory.notes`)
- `deque[maxlen=8]` por agente
- Ejemplos: `"Dron-1: objetivo en (15,8)"`, `"Sensor: (22,5)"`, `"compuerta activa"`
- **Visualización**: panel de monitoreo → contexto legible por humano

---

## 4. Métricas de Agente (Panel de Monitoreo)

Cada `PlanningAgent` expone:
```python
@property
def expanded_last(self) -> int:      # Nodos expandidos última búsqueda
@property
def cost_last(self) -> float:        # Coste ruta encontrada
@property
def ms_last(self) -> float:          # Tiempo búsqueda (ms)
def algorithm_used(self) -> str:     # "A*" o "Dijkstra"
```

**Panel muestra** (por agente seleccionado con TAB/1-4):
- Estado actual + objetivo textual
- Percepción (qué ve/recuerda)
- Memoria (avistamientos, cruces, aciertos predicción)
- Métricas última búsqueda (coste, expandidos, ms, pasos)
- **Comparativa Dijkstra vs A*** (barras, coste, nodos, ms, ACTIVO)
- Bloque específico: predicción (ARGOS), patrulla (Drones), decisión (Bot)

---

## 5. Extensibilidad: Añadir Nuevo Agente

```python
# 1. Subclase PlanningAgent (o Entity si no planifica)
class NuevoAgente(PlanningAgent):
    def __init__(self, maze):
        super().__init__("Nombre", start_tile, step_time, color, "Rol")
        # Atributos específicos...
    
    def think(self, game):
        # Percepción → Memoria → Decisión → Planificación
        pass
    
    def perception_text(self, game) -> str:
        return "Descripción legible de qué percibe"
    
    def memory_text(self, game) -> str:
        return "Descripción legible de memoria/contexto"

# 2. Instanciar en Game.__init__():
self.nuevo = NuevoAgente(self.maze)

# 3. Actualizar en Game.update():
self.nuevo.update(self, dt)

# 4. Añadir a panel en UIMixin._draw_tabs():
tabs.append(("NUEVO", color, 4))  # índice 4

# 5. Manejar en UIMixin._draw_specific():
if isinstance(agent, NuevoAgente):
    self._micro_label("BLOQUE ESPECÍFICO", x, y)
    ...
```

---

## 6. Diagramas de Secuencia Clave

### 6.1 ARGOS Detecta Jugador → Intercepción
```
Jugador pisa sensor
      │
      ▼
game._trigger_sensor() → game.raise_alarm()
      │
      ▼
argos.notify_sensor() → last_seen, heat += 1
      │
      ▼
argos.think_timer = 0.04 (replan inmediato)
      │
      ▼ [siguiente frame]
argos.think() → sees_player() = True
      │
      ├─▶ state = CAZA/INTERCEPTA
      ├─▶ prediction = predict_intercept(...)
      ├─▶ target = prediction.target
      └─▶ plan_to(game, {target}) → Dijkstra + A*
```

### 6.2 Drón Reporta → ARGOS Replanifica
```
Drón en think() → sees_player = True
      │
      ▼
game.drone_report(drone, player.tile)
      │
      ▼
argos.receive_report() → last_seen, heat += 2, notes
      │
      ▼
argos.think_timer = 0.04
      │
      ▼ [siguiente frame]
argos.think() → state = INVESTIGA/CAZA → plan_to()
```

### 6.3 Bloqueo de Corredor (ARGOS)
```
argos.think() → condiciones: ve/recuerda + lock_ready + security≥12
      │
      ▼
game.try_blockade("ARGOS", by_argos=True)
      │
      ├─▶ dijkstra(ruta actual Ícaro)
      ├─▶ busca puerta en ruta con alternativa válida
      ├─▶ bloquea puerta (graph.set_blocked + locked_doors)
      ├─▶ log_event("ARGOS", "bloquea puerta...")
      └─▶ memory.blocked_corridors += 1
```

---

## 7. Configuración de Balance (`config.py`)

| Constante | Valor | Efecto |
|-----------|-------|--------|
| `ARGOS_STEP_TIME` | 0.225 | Velocidad base movimiento |
| `ARGOS_STEP_MIN` | 0.176 | Velocidad máx con seguridad alta |
| `ARGOS_THINK_TIME` | 0.38 | Intervalo base replanificación |
| `ARGOS_VISION` | 8.5 | Radio visión (baldosas) |
| `ARGOS_MEMORY_TTL` | 12.0 | Segundos recordando last_seen |
| `ARGOS_LOCK_COOLDOWN` | 15.0 | Segundos entre bloqueos |
| `ARGOS_LOCK_AFTER` | 6.0 | Tiempo antes de primer bloqueo |
| `PREDICTION_DEPTH` | 4 | Profundidad árbol predicción |
| `PREDICTION_BUDGET` | 700 | Nodos máx predicción |
| `DRONE_COUNT` | 2 | Número de drones |
| `DRONE_VISION` | 6.0 | Radio visión drones |
| `DRONE_REPORT_COOLDOWN` | 4.0 | Segundos entre reportes |

---

## 8. Validación de Comportamiento (Tests)

```python
# tests/test_icaro.py
def test_blockade_has_valid_more_expensive_alternative(self):
    result = game.force_blockade()  # F5
    assert result is not None
    assert result["after"] > result["before"]  # Ruta más cara
    alternative = dijkstra(..., game.player_objectives())
    assert alternative.found
    assert result["door"] not in alternative.path  # Puerta no en nueva ruta

def test_drone_report_updates_argos_memory(self):
    drone.tile = adjacent_to_player
    drone.think(game)
    assert drone.reports == 1
    assert game.argos.last_seen == player.tile
```

---

## 9. Referencias de Diseño

- **Arquitectura BDI** (Beliefs-Desires-Intentions) simplificada: percepción=beliefs, objetivos=desires, plan=intentions
- **Subsumption architecture** (Brooks): capas de comportamiento (patrulla → investigación → caza → interceptación)
- **Blackboard pattern**: `Argos.heat` + `notes` como memoria compartida legible por todos los agentes
- **Recursive best-first search** adaptado para predicción acotada (Korf, 1993)