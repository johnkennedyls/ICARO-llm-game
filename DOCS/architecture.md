# Arquitectura del Sistema — El Escape de Ícaro

## 1. Visión General

El sistema sigue una **arquitectura por capas** con separación estricta entre:
- **Simulación pura** (`game.py`, `maze.py`, `graph.py`, `algorithms.py`, `planning.py`, `agents.py`) — sin dependencias de Pygame
- **Renderizado** (`render/`) — solo lectura del estado, sin lógica de juego
- **Aplicación** (`app.py`) — bucle principal, entrada, gestión de estados

Esto permite:
- Tests unitarios sin ventana gráfica (`SDL_VIDEODRIVER=dummy`)
- Experimentos headless masivos
- Reemplazo del motor gráfico sin tocar la simulación
- Replays deterministas (misma semilla = misma partida)

---

## 2. Módulos Principales

### 2.1 `config.py` — Constantes Centralizadas
Todas las constantes de balance, visuales y algorítmicas en un solo lugar. Modificar aquí cambia el comportamiento global sin tocar lógica.

### 2.2 `graph.py` — Grafo Ponderado Implícito (`GridGraph`)
```python
class GridGraph:
    open_tiles: set[Coord]        # Vértices transitables
    costs: dict[Coord, float]     # Coste de ENTRAR a cada baldosa
    blocked: set[Coord]           # Puertas cerradas (eliminación temporal)
```
- **Vértice**: cada baldosa transitable `(x, y)`
- **Arista**: conexión ortogonal (N/E/S/O) entre baldosas abiertas no bloqueadas
- **Peso**: coste de la baldosa *destino* (suelo=1, sensor=2, vapor=3, puerta=1)
- **Dinámico**: `set_blocked(tile, True/False)` permite cerrar/abrir puertas en caliente
- **Consultas**: `neighbors()`, `is_open()`, `reachable()`, `distance_map()`, `line_of_sight()`, `visible_tiles()`

### 2.3 `maze.py` — Generación Procedural Determinista
Algoritmo: **Recursive Backtracker** + **Braiding** (trenzado)
1. Genera laberinto perfecto (sin ciclos) con backtracking recursivo
2. **Braiding**: abre callejones sin salida (probabilidad 22%) → crea ciclos
3. **Bucles extra**: conecta pasillos paralelos para más alternativas
4. Coloca: inicio, salida, 3 tarjetas, puertas, sensores, vapor, terminales, agentes
5. **Garantía**: ruta inicio→salida/tarjetas siempre tiene al menos una puerta bloqueable con alternativa válida
6. **Costos**: asigna pesos a baldosas según tipo
7. **Validación**: verifica que todos los objetivos sean alcanzables desde inicio

**Determinismo**: `random.Random(seed)` — misma semilla = mismo mapa exacto.

### 2.4 `algorithms.py` — Dijkstra y A* Unificados
```python
def _search(graph, start, goals, *, algorithm, use_heuristic, reopen=False, cost_bias=None)
    -> SearchResult
```
- **Entrada**: mismo grafo, mismo origen, mismos destinos, mismos costos
- **Heurística**: `h(n) = min(manhattan(n, goal) for goal in goals)`
  - **Admisible**: coste mínimo de arista = 1, Manhattan ≤ pasos reales
  - **Consistente**: `h(u) ≤ cost(u,v) + h(v)` porque Manhattan es 1-Lipschitz y cost ≥ 1
  - **Resultado**: A* sin reaperturas (`reopen=False`) garantiza optimalidad
- **Desempate**: prioriza menor `h` en frontier → menos expansiones sin perder optimalidad
- **Métricas** (`SearchResult`): `expanded`, `generated`, `frontier_peak`, `elapsed_ms`, `reopenings`, `cost`, `path`, `found`

### 2.5 `planning.py` — Predicción Recursiva Acotada
```python
def predict_intercept(maze, argos_tile, player_tile, objectives, heat, depth=4, node_budget=700)
    -> PredictionResult
```
**Árbol de búsqueda** del escape futuro de Ícaro:
- **Caso base**: `depth == 0` OR `tile in objectives` OR `no legal moves` OR `nodes >= budget`
- **Progreso**: cada llamada consume `depth-1`, añade `tile` a `visited` (evita ciclos)
- **Ramificación**: ≤ 4 (grilla ortogonal), poda por `visited` y `argos_tile`
- **Ordenación**: movimientos que acercan a objetivos + calor de memoria (cruces frecuentes)
- **Salida**: `target` (intercepción óptima), `probable` (hoja más plausible), métricas

**Complejidad**: O(min(b^d, node_budget)) tiempo, O(d) espacio de pila.

### 2.6 `agents.py` — Agentes Autónomos

#### Clase Base: `PlanningAgent(Entity)`
- `plan_to(game, targets)` → ejecuta **Dijkstra Y A***, elige según `game.algorithm`
- `advance(game)` → mueve un paso por baldosa
- `path_blocked(game)` → detecta si siguiente baldosa ya no transitable
- Métricas: `expanded_last`, `cost_last`, `ms_last`, `algorithm_used()`

#### `Argos(PlanningAgent)` — Cazador Principal
**Estados**: `PATRULLA` → `INVESTIGA` → `CAZA` / `INTERCEPTA` → `PATRULLA`
- **Percepción**: visión directa (LOS) + reportes drones + sensores
- **Memoria**: `heat` (Counter de avistamientos), `crossings` (set de cruces ≥3 conexiones), `last_seen`, `last_seen_at` (TTL 12s)
- **Predicción**: `predict_intercept()` cada vez que ve al jugador
- **Bloqueo**: `try_blockade()` cada 15s (ajustable por seguridad) si ve/recuerda al jugador
- **Velocidad dinámica**: acelera con nivel de seguridad alto

#### `Drone(PlanningAgent)` — Exploradores (2)
- Patrullan ruta fija entre 2 puntos de patrulla
- **Visión**: radio 6 + LOS
- **Reporte**: cada 4s si ven al jugador → `game.drone_report()` → actualiza memoria ARGOS

#### `PlayerBot` — Piloto Automático de Ícaro
- Planifica hacia tarjetas/salida con **bias de riesgo** (penaliza radio ARGOS + predicción)
- Replanifica si: ruta bloqueada, objetivos cambian, cada 2s
- Evita caminar directo hacia ARGOS

#### `Player(Entity)` — Jugador Humano
- Control por teclado, energía, tarjetas, step_timer

### 2.7 `game.py` — Estado de Partida (Simulación Pura)
```python
class Game:
    maze: Maze
    player: Player
    argos: Argos
    drones: list[Drone]
    bot: PlayerBot
    time: float
    state: "playing" | "won" | "lost"
    security: float          # Nivel de alerta 0-100
    sensors_disabled_until: float
    reveal_until: float
    log: deque[LogEntry]     # 300 eventos máx
    search_stats: dict       # Métricas agregadas Dijkstra/A*
    acceptance_tests: list   # Pruebas F5
```
**Bucle `update(dt, move_dir)`**:
1. Tiempo + límite 180s
2. Desbloqueo puertas expiradas
3. Decaimiento seguridad / aumento si ARGOS ve jugador
4. Energía jugador (−0.85/s)
5. Movimiento jugador (manual o bot)
6. Colisión ARGOS → derrota
7. `argos.update()` + `drone.update()`
8. Colisión post-movimiento ARGOS → derrota

### 2.8 `session_log.py` — Logging Persistente
- Archivo: `logs/partida_<timestamp>_semilla<N>.log`
- Formato: `[tiempo] AGENTE   CATEGORIA  mensaje`
- Resumen final: métricas, pruebas de aceptación

### 2.9 `experiments.py` — Banco de Experimentos
- Escenarios: `salida`, `tarjetas`, `persecucion`
- Tamaños: Pequeño(10×7), Mediano(17×12), Grande(26×18), Muy grande(36×25)
- Semillas: 7, 21, 42, 99, 123 (configurable)
- Repeticiones: 5 por defecto
- Salida: CSV + Markdown con análisis estadístico

### 2.10 `render/` — Capa Gráfica
```
Renderer (ScreensMixin + UIMixin + WorldMixin)
├── base.py       # Utilidades: fuentes, formas, niebla, geometría mapa
├── world.py      # Mundo: baldosas, agentes, rutas, efectos, badges
├── ui.py         # HUD superior, panel derecho, pie de página
└── screens.py    # Pantallas: título, pausa, fin de partida
```
- **Niebla de guerra**: `visible_tiles()` + `explored` set, actualizado 11Hz
- **Escalado**: canvas fijo 1400×800 → ventana redimensionable con `smoothscale`
- **60 FPS** objetivo, `dt` clampeado a 0.10s

---

## 3. Flujo de Datos Principal

```
main.py
  └── App.run() [60 FPS]
        ├── dt = clock.tick(60)/1000
        ├── renderer.tick(dt)
        ├── _handle_events() → teclas → game.actions
        ├── _update(dt)
        │     └── game.update(dt, move_dir)
        │           ├── time += dt
        │           ├── player.update_visual(dt)
        │           ├── bot.update()  [si autopilot]
        │           ├── argos.update()  [think + step]
        │           └── drone.update()  [think + step]
        ├── _draw()
        │     ├── renderer.draw_game()  [world + ui]
        │     └── renderer.draw_pause/end/title  [si aplica]
        └── _present()  [escalado + flip]
```

---

## 4. Invariantes y Garantías

| Invariante | Dónde se garantiza |
|------------|-------------------|
| Mapa jugable (objetivos alcanzables) | `Maze._build_costs_and_graph()` + validación final |
| Puerta bloqueable con alternativa | `Maze._ensure_route_door()` + `try_blockade()` verifica antes de bloquear |
| Heurística consistente | `algorithms.heuristic_is_consistent()` + test unitario |
| Dijkstra y A* mismo grafo/origen/destino | `PlanningAgent.plan_to()` ejecuta ambos secuencialmente |
| Determinismo por semilla | `random.Random(seed)` en Maze, sin RNG global en simulación |
| Separación simulación/render | `Game` no importa `pygame`; `Renderer` solo lee `Game` |

---

## 5. Extensibilidad

### Añadir nuevo agente
1. Subclase `PlanningAgent` (o `Entity` si no planifica)
2. Implementar `think(game)` + `perception_text()` + `memory_text()`
3. Añadir a `Game.all_agents()` y pestañas en `UIMixin._draw_tabs()`

### Añadir nuevo tipo de baldosa
1. Constante coste en `config.py`
2. Generación en `Maze._place_<tipo>()`
3. Dibujo en `WorldMixin._draw_features()` + `_draw_<tipo>()`
4. Lógica de entrada en `Game.attempt_player_move()` si especial

### Añadir nuevo algoritmo de búsqueda
1. Función en `algorithms.py` siguiendo firma `_search()`
2. Registrar en `config.ALGO_*` y `ALGO_LABEL`
3. Añadir a `Game.toggle_algorithm()` y `PlanningAgent.plan_to()`
4. Métricas en `Game.search_stats` y `register_search()`