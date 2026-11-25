"""Predicción recursiva de la ruta de escape de Ícaro.

ARGOS explora un árbol acotado de movimientos futuros del jugador:

* **Caso base**: profundidad 0, nodo sin movimientos legales, Ícaro alcanzó
  uno de sus objetivos, o se agotó el presupuesto de nodos.
* **Progreso**: cada llamada consume un nivel de profundidad y añade la
  baldosa al conjunto ``visited`` de esa rama (evita ciclos).
* **Terminación**: ``depth`` y ``node_budget`` están acotados; el peor caso es
  O(b^d) nodos con b<=4 y d=4 por defecto.
* **Pila**: O(d) marcos por rama (más las hojas recolectadas).

Las hojas se ponderan por cercanía a los objetivos de Ícaro y por el mapa de
calor de avistamientos (memoria de cruces frecuentes). ARGOS elige, entre las
hojas más plausibles, la que puede alcanzar antes.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Iterable, Mapping

from . import config
from .graph import Coord, manhattan


@dataclass(slots=True)
class PredictionResult:
    target: Coord | None
    probable: Coord | None
    nodes: int
    leaves: int
    depth: int
    elapsed_ms: float
    truncated: bool
    rationale: str


def predict_intercept(
    maze,
    argos_tile: Coord,
    player_tile: Coord,
    objectives: Iterable[Coord],
    heat: Mapping[Coord, int] | None = None,
    depth: int = config.PREDICTION_DEPTH,
    node_budget: int = config.PREDICTION_BUDGET,
) -> PredictionResult:
    """Explora el árbol de escape y devuelve una baldosa de intercepción."""
    t0 = perf_counter()
    heat = heat or {}
    objective_set = tuple(dict.fromkeys(objectives))
    if not objective_set or depth <= 0:
        return PredictionResult(
            target=player_tile,
            probable=player_tile,
            nodes=0,
            leaves=0,
            depth=max(0, depth),
            elapsed_ms=(perf_counter() - t0) * 1000.0,
            truncated=False,
            rationale="sin objetivos o profundidad 0: perseguir posición actual",
        )

    leaves: list[tuple[Coord, int, int]] = []  # (baldosa, pasos, dist. objetivo)
    nodes = 0
    truncated = False

    def nearest_goal_distance(tile: Coord) -> int:
        return min(manhattan(tile, goal) for goal in objective_set)

    def explore(tile: Coord, remaining: int, visited: set[Coord], steps: int) -> None:
        nonlocal nodes, truncated
        if nodes >= node_budget:
            truncated = True
            return
        nodes += 1
        dist_goal = nearest_goal_distance(tile)

        if remaining == 0 or tile in objective_set:
            leaves.append((tile, steps, dist_goal))
            return

        options = []
        for nxt, _cost in maze.graph.neighbors(tile):
            if nxt == argos_tile or nxt in visited:
                continue
            options.append(nxt)

        if not options:
            leaves.append((tile, steps, dist_goal))
            return

        # Ordena primero los movimientos que más acercan a Ícaro a su meta.
        options.sort(
            key=lambda nxt: (
                nearest_goal_distance(nxt) - 1.4 * min(heat.get(nxt, 0), 6),
                nxt,
            )
        )
        for nxt in options:
            visited.add(nxt)
            explore(nxt, remaining - 1, visited, steps + 1)
            visited.remove(nxt)
            if truncated:
                return

    explore(player_tile, depth, {player_tile}, 0)

    if not leaves:
        target = player_tile
        rationale = "árbol sin hojas: se persigue la posición actual"
        probable = player_tile
    else:
        # Plausibilidad: cerca de los objetivos de Ícaro, con calor de memoria.
        ranked = sorted(
            leaves,
            key=lambda leaf: (
                leaf[2] - 2.0 * min(heat.get(leaf[0], 0), 6) + 0.08 * leaf[1],
                leaf[1],
            ),
        )
        probable_leaf = ranked[0]
        probable = probable_leaf[0]
        # Entre el tercio más plausible, elegir la hoja que ARGOS alcanza antes.
        cutoff = max(1, len(ranked) // 3)
        plausible = ranked[:cutoff]
        target_leaf = min(
            plausible,
            key=lambda leaf: (
                manhattan(argos_tile, leaf[0]) - 0.55 * leaf[1],
                leaf[2],
            ),
        )
        target = target_leaf[0]
        rationale = (
            f"árbol d={depth}: {nodes} nodos, {len(leaves)} hojas"
            + (" (podado)" if truncated else "")
            + f"; hoja probable {probable}"
        )

    return PredictionResult(
        target=target,
        probable=probable,
        nodes=nodes,
        leaves=len(leaves),
        depth=depth,
        elapsed_ms=(perf_counter() - t0) * 1000.0,
        truncated=truncated,
        rationale=rationale,
    )
