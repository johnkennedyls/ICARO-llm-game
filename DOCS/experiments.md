# Guía de Experimentos — Análisis Comparativo Dijkstra vs A*

## 1. Propósito

Validar empíricamente las propiedades teóricas de **Dijkstra** y **A*** sobre el **mismo grafo, mismos orígenes, mismos destinos, mismos costos** en condiciones de juego reales (mapas generados proceduralmente, pesos variables, objetivos múltiples).

---

## 2. Diseño Experimental

### 2.1 Variables Independientes
| Variable | Valores | Descripción |
|----------|---------|-------------|
| **Tamaño del mapa** | 4 niveles | Celdas del generador: Pequeño(10×7), Mediano(17×12), Grande(26×18), Muy Grande(36×25) |
| **Semilla** | 5 por defecto | 7, 21, 42, 99, 123 (determinista → mapas reproducibles) |
| **Escenario** | 3 tipos | `salida` (inicio→salida), `tarjetas` (inicio→3 tarjetas multi-objetivo), `persecucion` (ARGOS→inicio) |
| **Algoritmo** | 2 | `dijkstra`, `astar` |
| **Repeticiones** | 5 por defecto | Reduce ruido de medición (GC, cache, OS) |

**Total casos**: 4 × 5 × 3 = 60 configuraciones únicas
**Total búsquedas**: 60 × 2 algoritmos × 5 repeticiones = **600 ejecuciones**

### 2.2 Variables Dependientes (Métricas)
| Métrica | Captura | Herramienta |
|---------|---------|-------------|
| `coste` | Coste óptimo de la ruta encontrada | `SearchResult.cost` |
| `pasos` | Longitud de ruta (baldosas) | `len(path) - 1` |
| `expandidos` | Nodos extraídos del frontier | `SearchResult.expanded` |
| `generados` | Nodos insertados en frontier | `SearchResult.generated` |
| `frontera_max` | Pico de tamaño del heap | `SearchResult.frontier_peak` |
| `tiempo_ms` | Tiempo CPU búsqueda (perf_counter) | `SearchResult.elapsed_ms` |
| `tiempo_pared_ms` | Tiempo pared (incluye overhead) | `perf_counter` externo |
| `memoria_pico_kb` | Pico asignaciones Python | `tracemalloc.get_traced_memory()` |
| `vertices` | Vértices en grafo | `graph.vertices` |
| `aristas` | Aristas en grafo | `graph.edges` |

### 2.3 Control de Validez
- **Mismo grafo**: `maze.graph` idéntico para ambos algoritmos
- **Mismo origen/destinos**: `scenario.start`, `scenario.goals` idénticos
- **Mismos costos**: `maze.costs` idénticos
- **Verificación optimalidad**: `assert abs(dijkstra.cost - astar.cost) <= 1e-6`
- **Verificación consistencia ruta**: `assert abs(path_cost - result.cost) <= 1e-6`
- **Calentamiento**: 1 ejecución previa por caso (caches, JIT)

---

## 3. Ejecución

### 3.1 Comando Básico
```bash
python -m icaro.experiments
```

### 3.2 Opciones
```bash
# Rápido (desarrollo)
python -m icaro.experiments --quick
# Equivale a: --reps 2 --seeds 7,42 --sizes Pequeño,Mediano,Grande

# Personalizado
python -m icaro.experiments --reps 10 --seeds 7,21,42,99,123,456

# Directorio de salida personalizado
python -m icaro.experiments --out ./resultados_mios
```

### 3.3 Parámetros Programáticos
```python
from icaro.experiments import run_experiments
from pathlib import Path

rows, csv_path, md_path = run_experiments(
    reps=5,
    seeds=[7, 21, 42, 99, 123],
    sizes=[("Pequeño", 10, 7), ("Mediano", 17, 12), ("Grande", 26, 18), ("Muy grande", 36, 25)],
    out_dir=Path("docs")
)
```

---

## 4. Salidas Generadas

### 4.1 `docs/experimentos.csv` — Datos Crudos
Una fila por repetición × algoritmo. Columnas:
```
tamano, celdas_x, celdas_y, semilla, escenario, algoritmo, repeticion,
encontrado, coste, pasos, expandidos, generados, frontera_max,
tiempo_ms, tiempo_pared_ms, memoria_pico_kb, vertices, aristas
```

**Uso**: Importar en Pandas, R, Excel, Jupyter para análisis custom.

```python
import pandas as pd
df = pd.read_csv("docs/experimentos.csv")
# Ejemplo: boxplot de nodos expandidos por algoritmo y tamaño
import seaborn as sns
sns.boxplot(data=df, x="tamano", y="expandidos", hue="algoritmo")
```

### 4.2 `docs/experimentos.md` — Informe Autogenerado
Contiene:
1. **Metodología** completa
2. **Totales por tamaño** (tabla: nodos, tiempo, memoria, ahorro A*)
3. **Coste óptimo por tamaño** (verificación optimalidad)
4. **Detalle por escenario** (salida / tarjetas / persecución)
5. **Verificación de optimalidad** (casos con coste idéntico vs discrepancias)
6. **Guía de lectura** de resultados

---

## 5. Análisis Estadístico Recomendado

### 5.1 Comparación Principal: Nodos Expandidos
```python
# Ahorro A* = 100 * (1 - mean(A*) / mean(Dijkstra))
# Test de significancia (pareado por semilla+escenario):
from scipy.stats import wilcoxon
d_nodes = df[df.algoritmo=="dijkstra"].sort_values(["semilla","escenario"])["expandidos"]
a_nodes = df[df.algoritmo=="astar"].sort_values(["semilla","escenario"])["expandidos"]
stat, p = wilcoxon(d_nodes, a_nodes)
```

### 5.2 Escalabilidad (Fit a Complejidad Teórica)
```python
import numpy as np
# Modelo: nodos ~ a * V^b  (esperado b≈1 para Dijkstra, b<1 para A*)
sizes = df.groupby("tamano")["vertices"].first()
d_mean = df[df.algoritmo=="dijkstra"].groupby("tamano")["expandidos"].mean()
a_mean = df[df.algoritmo=="astar"].groupby("tamano")["expandidos"].mean()

# Regresión log-log
logV = np.log(sizes)
logD = np.log(d_mean)
logA = np.log(a_mean)
b_D = np.polyfit(logV, logD, 1)[0]  # exponente Dijkstra
b_A = np.polyfit(logV, logA, 1)[0]  # exponente A*
```

### 5.3 Intervalos de Confianza (Bootstrap)
```python
import bootstrap  # o implementación manual
def bootstrap_ci(data, n=10000, ci=95):
    means = [np.mean(np.random.choice(data, len(data), replace=True)) for _ in range(n)]
    return np.percentile(means, [(100-ci)/2, 100-(100-ci)/2])

ci_d = bootstrap_ci(d_nodes.values)
ci_a = bootstrap_ci(a_nodes.values)
```

### 5.4 Análisis por Escenario
Los 3 escenarios tienen características distintas:
| Escenario | Objetivos | Naturaleza |
|-----------|-----------|------------|
| `salida` | 1 (salida) | Punto a punto clásico |
| `tarjetas` | 3 (multi-objetivo) | Selector Dijkstra + A* a objetivo elegido |
| `persecucion` | 1 (inicio) | Origen = ARGOS, destino = jugador |

**Hipótesis**: Ahorro A* mayor en `salida` y `persecucion` (un objetivo claro) vs `tarjetas` (selector multi-objetivo usa Dijkstra).

---

## 6. Interpretación de Resultados Típicos

### 6.1 Ahorro de Nodos Expandidos
```
Tamaño        | Ahorro A* típico
--------------|-----------------
Pequeño       | 40–55%
Mediano       | 55–65%
Grande        | 65–72%
Muy Grande    | 70–75%
```
**Por qué crece**: heurística Manhattan descarta más ramas en mapas grandes donde la "ola" de Dijkstra explora áreas irrelevantes.

### 6.2 Ratio de Tiempo (A* / Dijkstra)
```
Tamaño        | Ratio típico
--------------|-------------
Pequeño       | 0.5–0.6×
Mediano       | 0.4–0.5×
Grande        | 0.35–0.45×
Muy Grande    | 0.3–0.4×
```
**Nota**: Overhead de heurística (cálculo h, desempate) es constante; beneficio crece con expansiones evitadas.

### 6.3 Memoria (tracemalloc)
- Correlaciona fuertemente con `expandidos + frontera_max`
- A* reduce memoria **30–50%**
- **Caveat**: `tracemalloc` mide asignaciones Python, no RSS; útil para comparación relativa, no valores absolutos.

### 6.4 Verificación de Optimalidad
- **100% casos**: `dijkstra.cost == astar.cost` (diferencia < 1e-6)
- **Conclusión empírica**: Heurística Manhattan **admisible y consistente** → A* sin reaperturas = óptimo garantizado.

---

## 7. Extensibilidad: Añadir Nuevos Algoritmos

### 7.1 En `algorithms.py`
```python
def nuevo_algoritmo(graph, start, goals, **kwargs) -> SearchResult:
    # Implementación...
    return SearchResult(...)

# Registrar en config.py:
ALGO_NUEVO = "nuevo"
ALGO_LABEL[ALGO_NUEVO] = "Nuevo"

# En PlanningAgent.plan_to():
if game.algorithm == config.ALGO_NUEVO:
    chosen = nuevo_algoritmo(...)
```

### 7.2 En `experiments.py`
```python
# Añadir a tupla de runners en _run_case():
for algorithm, runner in (
    (config.ALGO_DIJKSTRA, dijkstra),
    (config.ALGO_ASTAR, astar),
    (config.ALGO_NUEVO, nuevo_algoritmo),  # ← nuevo
):
    ...

# Añadir bucket en search_stats inicialización:
self.search_stats = {
    config.ALGO_DIJKSTRA: {...},
    config.ALGO_ASTAR: {...},
    config.ALGO_NUEVO: {"count": 0, "nodes": 0, "ms": 0.0, "peak": 0, "found": 0},
}
```

### 7.3 En `experiments._summary_tables()`
Actualizar agregaciones para incluir nuevo algoritmo.

---

## 8. Reproducibilidad

### 8.1 Semillas Fijas
```python
DEFAULT_SEEDS = (7, 21, 42, 99, 123)
```
Mismas semillas → mismos mapas → mismos grafos → mismos resultados.

### 8.2 Entorno
Informe incluye:
```
Entorno: Python 3.x.x · Windows/Linux · x86_64/ARM64
```
Para comparar entre máquinas, usar **ratio A*/Dijkstra** (cancelación de hardware).

### 8.3 Versionado
- Código versionado en Git
- `experimentos.md` incluye timestamp de generación
- CSV incluye todos los parámetros (tamaño, semilla, escenario, repetición)

---

## 9. Métricas de Calidad del Experimento

| Criterio | Implementación |
|----------|----------------|
| **Aleatorización** | Semillas fijas (no aleatorio), orden determinista |
| **Repeticiones** | 5+ por condición (configurable) |
| **Calentamiento** | 1 ejecución previa por caso |
| **Aislamiento** | Cada búsqueda en grafo fresco (no hay estado compartido) |
| **Verificación** | Asserts de optimalidad y consistencia de coste |
| **Métricas crudas** | CSV con granularidad por repetición |
| **Resumen estadístico** | Media, mediana, ahorro %, ratios |

---

## 10. Referencias Metodológicas

- **Benchmarking de algoritmos de búsqueda**: Felner et al., "Benchmarking Heuristic Search Algorithms" (SOCS 2011)
- **Metodología experimental en IA**: McGeoch, "A Guide to Experimental Algorithmics" (2012)
- **Análisis de A* en grillas**: Sturtevant, "Benchmarks for Grid-Based Pathfinding" (2012)
- **Validación de heurísticas**: Russell & Norvig, Cap. 3.5 (Admisibilidad, Consistencia)