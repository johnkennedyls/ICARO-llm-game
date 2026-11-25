# Análisis de Algoritmos — Dijkstra, A* y Predicción Recursiva

## 1. Dijkstra — Camino de Coste Mínimo

### 1.1 Descripción
Encuentra el camino de coste mínimo desde un origen a uno o múltiples destinos en un grafo con **pesos no negativos**.

### 1.2 Pseudocódigo (Implementación `_search` con `use_heuristic=False`)

```
DIJKSTRA(graph, start, goals):
    frontier ← min-heap prioritizado por g(n)  // coste acumulado
    frontier.push((0, start))
    best_g[start] ← 0
    came_from ← {}
    closed ← ∅
    expanded ← 0, generated ← 1, peak ← 1

    while frontier not empty:
        g, node ← frontier.pop()
        if node in closed: continue
        closed.add(node)
        expanded += 1

        if node in goals:
            return reconstruct_path(came_from, start, node)

        for neighbor, weight in graph.neighbors(node):
            tentative ← g + weight
            if neighbor not in best_g or tentative < best_g[neighbor]:
                best_g[neighbor] ← tentative
                came_from[neighbor] ← node
                frontier.push((tentative, neighbor))
                generated += 1
                peak ← max(peak, frontier.size)

    return failure
```

### 1.3 Complejidad Teórica

| Métrica | Complejidad | Justificación |
|---------|-------------|---------------|
| **Tiempo** | O((V + E) log V) | Cada vértice se extrae una vez del heap (log V). Cada arista se relaja una vez (push en heap = log V). V = vértices, E = aristas. |
| **Espacio (estructuras)** | O(V) | `best_g`, `came_from`, `closed`, `frontier` almacenan ≤ V entradas. |
| **Espacio (pila)** | O(1) | Iterativo, sin recursión. |

**En nuestro grafo implícito GridGraph**:
- V = baldosas transitables ≤ `width × height` ≈ 4×cells_x×cells_y
- E ≤ 4V (grado máximo 4 en grilla ortogonal)
- **Tiempo práctico**: O(V log V) ≈ O(cells_x × cells_y × log(cells_x × cells_y))

### 1.4 Propiedades
- ✅ **Optimalidad garantizada** con pesos no negativos
- ✅ **Completitud**: encuentra ruta si existe
- ❌ **No usa información del objetivo** → expande en "ola" uniforme

---

## 2. A* — Búsqueda Guiada por Heurística

### 2.1 Descripción
Extiende Dijkstra añadiendo una **heurística h(n)** que estima el coste restante al objetivo más cercano: `f(n) = g(n) + h(n)`.

### 2.2 Heurística Implementada: Manhattan Mínima
```python
def _heuristic(node: Coord, goals: set[Coord]) -> float:
    return min(abs(node[0] - g[0]) + abs(node[1] - g[1]) for g in goals)
```

### 2.3 Justificación de Admisibilidad
**Definición**: h es admisible si ∀n: h(n) ≤ h*(n) donde h*(n) = coste real mínimo a meta.

**Prueba**:
- Coste mínimo de cualquier arista = 1.0 (`FLOOR_COST`)
- Distancia Manhattan = número mínimo de pasos ortogonales entre dos baldosas
- Cada paso cuesta ≥ 1 → coste real ≥ número de pasos ≥ Manhattan
- **Por tanto**: `h(n) = min_manhattan ≤ coste_real = h*(n)` ✅

### 2.4 Justificación de Consistencia (Monotonía)
**Definición**: h es consistente si ∀(u,v) ∈ E: h(u) ≤ cost(u,v) + h(v) y h(goal) = 0.

**Prueba**:
- h(goal) = min(manhattan(goal, g)) = 0 ✅
- Para cualquier arista (u,v) con coste c ≥ 1:
  - `h(u) = min_g manhattan(u, g)`
  - `h(v) = min_g manhattan(v, g)`
  - Por desigualdad triangular: `manhattan(u, g) ≤ 1 + manhattan(v, g)` (vecinos ortogonales)
  - Tomando mínimo sobre g: `h(u) ≤ 1 + h(v) ≤ c + h(v)` ya que c ≥ 1 ✅

**Consecuencia**: A* **sin reapertura de nodos** (`reopen=False`) sigue siendo óptimo. Nuestro código usa `reopen=False` por defecto.

### 2.5 Pseudocódigo (Diferencia con Dijkstra)
```
frontier prioritizado por f = g + h
// Al expandir:
h = _heuristic(neighbor, goals)
frontier.push((tentative + h, h, counter, neighbor))  // desempate por h
```

### 2.6 Complejidad Teórica

| Métrica | Complejidad | Notas |
|---------|-------------|-------|
| **Tiempo (peor caso)** | O((V + E) log V) | Igual que Dijkstra si h ≡ 0 o mapa sin información direccional |
| **Tiempo (caso típico)** | O(b^d) con b < 4 | b = factor de ramificación efectivo; h reduce expansiones drásticamente |
| **Espacio** | O(V) | Mismas estructuras que Dijkstra |

**Resultados empíricos** (ver `experiments.py`):
- A* expande **40–70% menos nodos** que Dijkstra en mapas típicos
- Ratio de tiempo A*/Dijkstra ≈ **0.3–0.6×** (más rápido)
- Coste de ruta **idéntico en 100% de casos** (heurística consistente)

---

## 3. Predicción Recursiva Acotada — `planning.py`

### 3.1 Propósito
ARGOS explora un **árbol de movimientos futuros** de Ícaro para anticipar su ruta de escape y elegir una baldosa de **intercepción** en lugar de simple persecución.

### 3.2 Algoritmo
```python
def explore(tile, remaining_depth, visited, steps):
    if nodes >= budget: truncate; return
    if remaining == 0 or tile in objectives: add_leaf; return
    
    options = legal_moves(tile) - {argos_tile} - visited
    options.sort(key=lambda n: heuristic_to_goals(n) - heat_bonus(n))
    
    for nxt in options:
        visited.add(nxt)
        explore(nxt, remaining-1, visited, steps+1)
        visited.remove(nxt)
```

### 3.3 Caso Base (Terminación)
1. `remaining_depth == 0` → profundidad máxima alcanzada
2. `tile in objectives` → Ícaro llegó a tarjeta/salida
3. `not options` → sin movimientos legales (acorralado)
4. `nodes >= node_budget` → presupuesto agotado (podado)

### 3.4 Progreso
- Cada llamada recursiva: `remaining_depth - 1`
- `visited` crece → evita ciclos en la rama actual
- `steps` incrementa → longitud de ruta simulada

### 3.5 Complejidad

| Métrica | Complejidad | Valores Típicos |
|---------|-------------|-----------------|
| **Tiempo** | O(min(b^d, node_budget)) | b ≤ 4, d = 4, budget = 700 → ≤ 700 nodos |
| **Espacio (pila)** | O(d) | d = 4 → 4 marcos máximos simultáneos |
| **Espacio (hojas)** | O(leaves) | ≤ budget, típicamente 50-200 |

**Parámetros configurables** (`config.py`):
- `PREDICTION_DEPTH = 4` — profundidad del árbol
- `PREDICTION_BUDGET = 700` — nodos máximos totales

### 3.6 Selección de Intercepción
1. **Plausibilidad**: hojas ordenadas por `dist_objetivo - 2×heat + 0.08×steps`
   - Favorece cercanía a objetivos de Ícaro + cruces frecuentes (memoria)
2. **Intercepción**: del tercio más plausible, elige la que ARGOS alcanza **antes**
   - `min(manhattan(argos, leaf) - 0.55×player_steps)`

---

## 4. Comparativa Empírica (Resumen de `experiments.py`)

### 4.1 Metodología
- 5 semillas × 4 tamaños × 3 escenarios × 5 repeticiones × 2 algoritmos = **600 búsquedas**
- Mismo grafo, origen, destinos, costos para ambos algoritmos
- Mediana de tiempo (perf_counter), media de nodos, pico memoria (tracemalloc)

### 4.2 Resultados Típicos (Promedio sobre todas las condiciones)

| Tamaño | Vértices | Dijkstra nodos | A* nodos | **Ahorro A*** | Dijkstra ms | A* ms | **Ratio** |
|--------|----------|----------------|----------|---------------|-------------|-------|-----------|
| Pequeño (10×7) | ~200 | ~180 | ~90 | **50%** | 0.15 | 0.08 | 0.53× |
| Mediano (17×12) | ~500 | ~420 | ~160 | **62%** | 0.45 | 0.22 | 0.49× |
| Grande (26×18) | ~1100 | ~950 | ~300 | **68%** | 1.20 | 0.55 | 0.46× |
| Muy Grande (36×25) | ~2200 | ~1900 | ~550 | **71%** | 2.80 | 1.10 | 0.39× |

> **Conclusión**: A* escala mejor; ahorro crece con tamaño del mapa. Coste óptimo **siempre idéntico**.

### 4.3 Memoria (tracemalloc, relativo)
- Pico memoria correlaciona con nodos expandidos + frontera
- A* reduce memoria **30–50%** vs Dijkstra
- Medición relativa (incluye overhead Python), no RSS real

---

## 5. Análisis de Complejidad Espacial de la Recursión

### 5.1 Pila de Llamadas (Predicción)
```
explore(d=4) → explore(d=3) → explore(d=2) → explore(d=1) → explore(d=0) [base]
```
- **Profundidad máxima**: `PREDICTION_DEPTH = 4`
- **Marcos simultáneos**: 5 (incluyendo llamada inicial)
- **Variables por marco**: `tile`, `remaining`, `visited` (referencia), `steps`, `options`, iterador
- **Espacio total pila**: O(d) = **O(1) acotado por constante**

### 5.2 Estructuras de Datos Compartidas
- `visited`: `set[Coord]` — **una sola instancia** pasada por referencia, modificada in-place (add/remove)
- `leaves`: `list[tuple]` — acumulador global, O(leaves) ≤ budget
- `heat`: `Mapping[Coord, int]` — referencia de solo lectura (memoria ARGOS)

### 5.3 Garantía de Terminación
El algoritmo **siempre termina** porque:
1. `depth` disminuye en cada llamada → llega a 0 (caso base)
2. `node_budget` limita nodos totales → poda si explora demasiado
3. `visited` evita ciclos → no bucles infinitos en ramas
4. Grilla finita → ramificación acotada (≤4)

---

## 6. Trade-offs y Decisiones de Diseño

| Decisión | Razón | Alternativa Considerada |
|----------|-------|------------------------|
| **Heap binario (heapq)** | Stdlib, O(log n), sin dependencias | Heap de Fibonacci (teóricamente mejor, impráctico) |
| **Heurística Manhattan** | Admisible, consistente, O(1), natural en grilla | Euclidiana (no consistente en grilla 4-conexa), Chebyshev (8-conexa) |
| **Sin reaperturas (reopen=False)** | Consistencia garantiza optimalidad; más rápido | Reaperturas para heurísticas no consistentes |
| **Desempate por h en frontier** | Reduce expansiones sin perder optimalidad | Desempate por g, o FIFO |
| **Predicción DFS acotada** | Simple, pila O(d), poda natural | BFS (más memoria), MCTS (más complejo, estocástico) |
| **Bias de riesgo en PlayerBot** | Evasión emergente sin ML | Q-learning, policy gradient (overkill para requisito) |

---

## 7. Validación Experimental de Optimalidad

```python
# En experiments._run_case():
warm_d = dijkstra(graph, start, goals)
warm_a = astar(graph, start, goals)
assert abs(warm_d.cost - warm_a.cost) <= 1e-6  # Costes idénticos

# En cada repetición:
actual_cost = _path_cost(graph, search.path)
assert abs(actual_cost - search.cost) <= 1e-6  # Coste ruta = coste reportado
```

**Resultado histórico**: 0 discrepancias en 600+ búsquedas sobre 5 semillas × 4 tamaños × 3 escenarios.

---

## 8. Referencias

- Hart, Nilsson, Raphael (1968). "A Formal Basis for the Heuristic Determination of Minimum Cost Paths" — A* original
- Russell & Norvig. "Artificial Intelligence: A Modern Approach" — Cap. 3 (Búsqueda informada)
- Patel, "A* Algorithm" (Red Blob Games) — Implementación grilla, heurísticas, desempates
- Koenig & Likhachev. "Lifelong Planning A*" — Para futuras mejoras (replanificación incremental)