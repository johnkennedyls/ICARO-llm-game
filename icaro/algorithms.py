"""Dijkstra y A* sobre el mismo grafo ponderado no negativo.

Ambos algoritmos devuelven una :class:`SearchResult` con la ruta, su coste y
las métricas usadas por el panel de monitoreo y por los experimentos:
nodos expandidos, nodos generados, pico de frontera, tiempo y reaperturas.

Heurística
----------
``h(n) = min(dist_manhattan(n, meta) para meta en metas)``.

* Es admisible: ninguna arista cuesta menos de 1 y la distancia Manhattan es
  una cota inferior del número de pasos necesarios.
* Es consistente: h(meta)=0 y para cualquier arista (u, v) de coste c >= 1 se
  cumple h(u) <= c + h(v), porque h es 1-Lipschitz y c >= 1.
* Por ser consistente, A* sin reapertura de nodos sigue siendo óptimo.

La opción ``reopen=True`` permite experimentar con reapertura de nodos (útil
para discutir el caso de heurísticas no consistentes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from heapq import heappop, heappush
from itertools import count
from time import perf_counter
from typing import Iterable, Mapping

from .graph import Coord, GridGraph, manhattan

ALGORITHM_LABEL = {"astar": "A*", "dijkstra": "Dijkstra"}
EPS = 1e-9


@dataclass(slots=True)
class SearchResult:
    algorithm: str
    start: Coord
    goals: tuple[Coord, ...]
    goal: Coord | None
    path: list[Coord]
    cost: float
    expanded: int
    generated: int
    frontier_peak: int
    elapsed_ms: float
    found: bool
    reopenings: int = 0
    heuristic: str = "Manhattan"
    peaked_memory_kb: float = 0.0
    extra: dict[str, float] = field(default_factory=dict)

    @property
    def steps(self) -> int:
        return max(0, len(self.path) - 1)

    @property
    def algorithm_label(self) -> str:
        return ALGORITHM_LABEL.get(self.algorithm, self.algorithm)

    def as_row(self) -> dict[str, object]:
        return {
            "algorithm": self.algorithm,
            "found": self.found,
            "start": self.start,
            "goal": self.goal,
            "cost": round(self.cost, 6),
            "steps": self.steps,
            "expanded": self.expanded,
            "generated": self.generated,
            "frontier_peak": self.frontier_peak,
            "elapsed_ms": round(self.elapsed_ms, 6),
            "reopenings": self.reopenings,
            "heuristic": self.heuristic,
            "path": self.path,
        }


def _normalize_goals(goals: Coord | Iterable[Coord]) -> set[Coord]:
    if isinstance(goals, tuple) and len(goals) == 2 and all(isinstance(v, int) for v in goals):
        return {goals}  # type: ignore[return-value]
    return set(goals)


def _heuristic(node: Coord, goals: set[Coord]) -> float:
    # min de distancias Manhattan: 1-Lipschitz, admisible y consistente.
    return min(abs(node[0] - g[0]) + abs(node[1] - g[1]) for g in goals)


def _reconstruct(came_from: dict[Coord, Coord], start: Coord, goal: Coord) -> list[Coord]:
    path = [goal]
    node = goal
    while node != start:
        node = came_from[node]
        path.append(node)
    path.reverse()
    return path


def _search(
    graph: GridGraph,
    start: Coord,
    goals: set[Coord],
    *,
    algorithm: str,
    use_heuristic: bool,
    reopen: bool = False,
    cost_bias: Mapping[Coord, float] | None = None,
) -> SearchResult:
    t0 = perf_counter()
    goals = set(goals)
    goals_t = tuple(sorted(goals))
    heuristic_name = "Manhattan (mín. a metas)" if use_heuristic else "sin heurística"
    bias = cost_bias or {}

    def failure(expanded: int = 0, generated: int = 0, peak: int = 0) -> SearchResult:
        return SearchResult(
            algorithm=algorithm,
            start=start,
            goals=goals_t,
            goal=None,
            path=[],
            cost=float("inf"),
            expanded=expanded,
            generated=generated,
            frontier_peak=peak,
            elapsed_ms=(perf_counter() - t0) * 1000.0,
            found=False,
            heuristic=heuristic_name,
        )

    if not goals or not graph.is_open(start):
        return failure()

    counter = count()
    h0 = _heuristic(start, goals) if use_heuristic else 0.0
    frontier: list[tuple[float, float, int, Coord]] = [(h0, h0, next(counter), start)]
    best_g: dict[Coord, float] = {start: 0.0}
    came_from: dict[Coord, Coord] = {}
    closed: set[Coord] = set()
    expanded = 0
    generated = 1
    peak = 1
    reopenings = 0

    while frontier:
        _, _, _, node = heappop(frontier)
        if node in closed and not reopen:
            continue
        closed.add(node)
        expanded += 1

        if node in goals:
            path = _reconstruct(came_from, start, node)
            return SearchResult(
                algorithm=algorithm,
                start=start,
                goals=goals_t,
                goal=node,
                path=path,
                cost=best_g[node],
                expanded=expanded,
                generated=generated,
                frontier_peak=peak,
                elapsed_ms=(perf_counter() - t0) * 1000.0,
                found=True,
                reopenings=reopenings,
                heuristic=heuristic_name,
            )

        g_node = best_g[node]
        for nxt, weight in graph.neighbors(node):
            tentative = g_node + weight + bias.get(nxt, 0.0)
            known = best_g.get(nxt)
            if known is None or tentative < known - EPS:
                best_g[nxt] = tentative
                came_from[nxt] = node
                if nxt in closed:
                    if reopen:
                        closed.discard(nxt)
                        reopenings += 1
                    else:
                        # Con heurística consistente esto no ocurre.
                        continue
                h = _heuristic(nxt, goals) if use_heuristic else 0.0
                # Desempate por h: reduce expansiones sin perder optimalidad.
                heappush(frontier, (tentative + h, h, next(counter), nxt))
                generated += 1
                peak = max(peak, len(frontier))

    return failure(expanded, generated, peak)


def dijkstra(
    graph: GridGraph,
    start: Coord,
    goals: Coord | Iterable[Coord],
    *,
    reopen: bool = False,
    cost_bias: Mapping[Coord, float] | None = None,
) -> SearchResult:
    """Camino de coste mínimo con pesos no negativos (sin heurística)."""
    return _search(
        graph,
        start,
        _normalize_goals(goals),
        algorithm="dijkstra",
        use_heuristic=False,
        reopen=reopen,
        cost_bias=cost_bias,
    )


def astar(
    graph: GridGraph,
    start: Coord,
    goals: Coord | Iterable[Coord],
    *,
    reopen: bool = False,
    cost_bias: Mapping[Coord, float] | None = None,
) -> SearchResult:
    """A* con heurística Manhattan admisible y consistente."""
    return _search(
        graph,
        start,
        _normalize_goals(goals),
        algorithm="astar",
        use_heuristic=True,
        reopen=reopen,
        cost_bias=cost_bias,
    )


def compare(
    graph: GridGraph,
    start: Coord,
    goals: Coord | Iterable[Coord],
) -> tuple[SearchResult, SearchResult]:
    """Ejecuta Dijkstra y A* sobre el mismo origen, metas y costes."""
    return dijkstra(graph, start, goals), astar(graph, start, goals)


def heuristic_value(node: Coord, goals: Iterable[Coord]) -> float:
    """h(n) para mostrar en el panel."""
    return _heuristic(node, set(goals))


def heuristic_is_consistent(graph: GridGraph, goals: Iterable[Coord]) -> bool:
    """Comprueba empíricamente h(u) <= c(u,v) + h(v) en todas las aristas."""
    goal_set = set(goals)
    for tile in graph.open_tiles:
        if tile in graph.blocked:
            continue
        hu = _heuristic(tile, goal_set)
        for nxt, cost in graph.neighbors(tile):
            if hu > cost + _heuristic(nxt, goal_set) + EPS:
                return False
    return True
