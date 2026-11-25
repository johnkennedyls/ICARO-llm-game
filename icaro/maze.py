"""Generación procedural del laberinto y de sus elementos de juego.

El laberinto se genera con *recursive backtracker* y luego se "trenza"
(braiding): se abren algunos callejones sin salida para crear ciclos. Esos
ciclos son imprescindibles para que, al bloquear un corredor, exista una ruta
alternativa y los agentes tengan que replanificar.

Baldosas especiales y sus costes de entrada:
    suelo 1 · sensor 2 · vapor 3 · puerta 1 (cerrada = no transitable)

Semillas: toda la generación es determinista para una semilla dada.
"""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from . import config
from .algorithms import dijkstra
from .graph import NEIGHBOR_ORDER, Coord, GridGraph, manhattan

DIRS: tuple[Coord, ...] = NEIGHBOR_ORDER


@dataclass(slots=True)
class DoorInfo:
    tile: Coord
    orientation: str  # "horizontal" (pasillo E-O) o "vertical" (pasillo N-S)


class Maze:
    """Laberinto 2D y su grafo ponderado asociado."""

    def __init__(self, cells_x: int = config.DEFAULT_CELLS_X,
                 cells_y: int = config.DEFAULT_CELLS_Y, seed: int = config.DEFAULT_SEED):
        if cells_x < 4 or cells_y < 4:
            raise ValueError("el mapa debe tener al menos 4x4 celdas")
        self.cells_x = cells_x
        self.cells_y = cells_y
        self.seed = seed
        self.width = 2 * cells_x + 1
        self.height = 2 * cells_y + 1
        self.rng = random.Random(seed)
        self.locked_doors: dict[Coord, float] = {}

        self.width_tiles = self.width
        self.height_tiles = self.height

        self.open_tiles: set[Coord] = set()
        self._generate_layout()
        self._place_start_exit_cards()
        self.doors: set[Coord] = set()
        self.door_infos: dict[Coord, DoorInfo] = {}
        self._place_doors()
        self.sensors: set[Coord] = set()
        self._place_sensors()
        self.hazards: set[Coord] = set()
        self._place_hazards()
        self.terminals: set[Coord] = set()
        self._place_terminals()
        self._place_agents_and_patrols()
        self._build_costs_and_graph()

    # ------------------------------------------------------------------
    # Construcción del trazado
    # ------------------------------------------------------------------
    def _cell_center(self, cx: int, cy: int) -> Coord:
        return 2 * cx + 1, 2 * cy + 1

    def _generate_layout(self) -> None:
        self.open_tiles.add(self._cell_center(0, 0))
        visited = {(0, 0)}
        stack = [(0, 0)]
        while stack:
            cx, cy = stack[-1]
            options = [
                (cx + dx, cy + dy)
                for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))
                if 0 <= cx + dx < self.cells_x
                and 0 <= cy + dy < self.cells_y
                and (cx + dx, cy + dy) not in visited
            ]
            if not options:
                stack.pop()
                continue
            nxt = self.rng.choice(options)
            nx, ny = nxt
            x1, y1 = self._cell_center(cx, cy)
            x2, y2 = self._cell_center(nx, ny)
            self.open_tiles.add(((x1 + x2) // 2, (y1 + y2) // 2))
            self.open_tiles.add((x2, y2))
            visited.add(nxt)
            stack.append(nxt)

        # Trenzado: abrir callejones sin salida para generar ciclos.
        dead_ends = [
            self._cell_center(cx, cy)
            for cy in range(self.cells_y)
            for cx in range(self.cells_x)
            if self._degree_raw(self._cell_center(cx, cy)) <= 1
        ]
        self.rng.shuffle(dead_ends)
        for tile in dead_ends:
            if self.rng.random() > 0.78:
                continue
            cx, cy = tile[0] // 2, tile[1] // 2
            wall_options: list[Coord] = []
            for dx, dy in DIRS:
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < self.cells_x and 0 <= ny < self.cells_y):
                    continue
                x2, y2 = self._cell_center(nx, ny)
                wall = ((tile[0] + x2) // 2, (tile[1] + y2) // 2)
                if wall not in self.open_tiles:
                    wall_options.append(wall)
            if wall_options:
                self.open_tiles.add(self.rng.choice(wall_options))

        # Bucles adicionales entre pasillos paralelos.
        extra_budget = max(2, len(self.open_tiles) // 55)
        candidates: list[Coord] = []
        for y in range(1, self.height - 1):
            for x in range(1, self.width - 1):
                tile = (x, y)
                if tile in self.open_tiles:
                    continue
                left = (x - 1, y) in self.open_tiles
                right = (x + 1, y) in self.open_tiles
                up = (x, y - 1) in self.open_tiles
                down = (x, y + 1) in self.open_tiles
                if (left and right) or (up and down):
                    candidates.append(tile)
        self.rng.shuffle(candidates)
        for tile in candidates[:extra_budget]:
            self.open_tiles.add(tile)

        # Conectividad de seguridad: todo punto abierto debe ser alcanzable.
        if not self.open_tiles:
            raise RuntimeError("laberinto vacío")
        start = next(iter(self.open_tiles))
        reachable = self._reachable_open(start)
        if reachable != self.open_tiles:
            self.open_tiles = reachable

    def _degree_raw(self, tile: Coord) -> int:
        x, y = tile
        return sum(
            1 for dx, dy in DIRS if (x + dx, y + dy) in self.open_tiles
        )

    def _neighbors_open(self, tile: Coord) -> list[Coord]:
        x, y = tile
        return [
            (x + dx, y + dy)
            for dx, dy in DIRS
            if (x + dx, y + dy) in self.open_tiles
        ]

    def _reachable_open(self, start: Coord, extra_blocked: Iterable[Coord] = ()) -> set[Coord]:
        extra = set(extra_blocked)
        if start not in self.open_tiles or start in extra:
            return set()
        seen = {start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            x, y = node
            for dx, dy in DIRS:
                nxt = (x + dx, y + dy)
                if nxt in seen or nxt in extra or nxt not in self.open_tiles:
                    continue
                seen.add(nxt)
                queue.append(nxt)
        return seen

    def _bfs_path(self, start: Coord, goal: Coord,
                  extra_blocked: Iterable[Coord] = ()) -> list[Coord]:
        extra = set(extra_blocked)
        if start == goal:
            return [start]
        parent: dict[Coord, Coord] = {start: start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            if node == goal:
                break
            x, y = node
            for dx, dy in DIRS:
                nxt = (x + dx, y + dy)
                if nxt in parent or nxt in extra or nxt not in self.open_tiles:
                    continue
                parent[nxt] = node
                queue.append(nxt)
        if goal not in parent:
            return []
        path = [goal]
        while path[-1] != start:
            path.append(parent[path[-1]])
        path.reverse()
        return path

    def _distance_map_raw(self, start: Coord) -> dict[Coord, int]:
        dist = {start: 0}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            x, y = node
            for dx, dy in DIRS:
                nxt = (x + dx, y + dy)
                if nxt in dist or nxt not in self.open_tiles:
                    continue
                dist[nxt] = dist[node] + 1
                queue.append(nxt)
        return dist

    # ------------------------------------------------------------------
    # Personajes y objetivos
    # ------------------------------------------------------------------
    def _place_start_exit_cards(self) -> None:
        corners = [(0, 0), (self.cells_x - 1, 0),
                   (0, self.cells_y - 1), (self.cells_x - 1, self.cells_y - 1)]
        corner = self.rng.choice(corners)
        self.start = self._cell_center(*corner)
        self.dist_from_start = self._distance_map_raw(self.start)

        # Salida: baldosa lo más lejana posible y, a ser posible, con cruce.
        by_distance = sorted(
            self.dist_from_start.items(), key=lambda item: item[1], reverse=True
        )
        far_tiles = [tile for tile, dist in by_distance[: max(8, len(by_distance) // 10)]]
        junction_far = [t for t in far_tiles if self._degree_raw(t) >= 2]
        self.exit = self.rng.choice(junction_far or far_tiles or [self.start])

        # Tarjetas: muestreo de punto más lejano respecto a inicio y tarjetas.
        selected: list[Coord] = []
        distance_maps: list[dict[Coord, int]] = [self.dist_from_start]
        candidates = [
            t for t in self.open_tiles
            if t != self.start and t != self.exit and self.dist_from_start.get(t, 0) >= 4
        ]
        if not candidates:
            candidates = [t for t in self.open_tiles if t != self.start]
        for _ in range(config.CARD_COUNT):
            best_tile = None
            best_score = -1.0
            for tile in candidates:
                if tile in selected:
                    continue
                near_selected = min(
                    (dm.get(tile, 10**9) for dm in distance_maps), default=0
                )
                near_exit = manhattan(tile, self.exit)
                score = near_selected * 1.0 + self.dist_from_start.get(tile, 0) * 0.35
                if near_exit <= 2:
                    score -= 5.0
                score += self.rng.random() * 0.01
                if score > best_score:
                    best_score = score
                    best_tile = tile
            if best_tile is None:
                break
            selected.append(best_tile)
            distance_maps.append(self._distance_map_raw(best_tile))
            candidates = [t for t in candidates if t != best_tile]
        while len(selected) < config.CARD_COUNT and candidates:
            selected.append(self.rng.choice(candidates))
        self.cards: tuple[Coord, ...] = tuple(selected)

        self.important_tiles: set[Coord] = {self.start, self.exit, *self.cards}

    # ------------------------------------------------------------------
    # Puertas
    # ------------------------------------------------------------------
    def _door_orientation_raw(self, tile: Coord) -> str | None:
        x, y = tile
        if tile not in self.open_tiles:
            return None
        left = (x - 1, y) in self.open_tiles
        right = (x + 1, y) in self.open_tiles
        up = (x, y - 1) in self.open_tiles
        down = (x, y + 1) in self.open_tiles
        if left and right and not up and not down:
            return "horizontal"
        if up and down and not left and not right:
            return "vertical"
        return None

    def _door_has_alternative(self, tile: Coord) -> bool:
        """¿Sigue habiendo ruta a todos los objetivos si se cierra la puerta?"""
        reachable = self._reachable_open(self.start, extra_blocked={tile})
        return all(t in reachable for t in self.important_tiles)

    def _place_doors(self) -> None:
        target_count = max(3, min(7, len(self.open_tiles) // 95 + 2))
        relevant_paths = []
        for objective in (self.exit, self.cards[0] if self.cards else self.exit):
            path = self._bfs_path(self.start, objective)
            if path:
                relevant_paths.append(path)

        # Puerta garantizada sobre el corredor óptimo inicio→salida/tarjeta.
        guaranteed: Coord | None = None
        for path in relevant_paths:
            middle = path[max(1, len(path) // 3): max(2, (2 * len(path)) // 3)]
            self.rng.shuffle(middle)
            for tile in middle:
                if self._door_orientation_raw(tile) is None:
                    continue
                if tile in self.important_tiles:
                    continue
                if self._door_has_alternative(tile):
                    guaranteed = tile
                    break
            if guaranteed:
                break

        if guaranteed:
            self.doors.add(guaranteed)

        # Puertas adicionales en corredores rectos, bien repartidas.
        candidates: list[Coord] = []
        for tile in self.open_tiles:
            if tile in self.doors or tile in self.important_tiles:
                continue
            if self._door_orientation_raw(tile) is None:
                continue
            if self.doors and min(manhattan(tile, other) for other in self.doors) < 3:
                continue
            candidates.append(tile)
        self.rng.shuffle(candidates)
        for tile in candidates:
            if len(self.doors) >= target_count:
                break
            if min((manhattan(tile, other) for other in self.doors), default=99) < 3:
                continue
            self.doors.add(tile)

        for tile in self.doors:
            orientation = self._door_orientation_raw(tile) or "horizontal"
            self.door_infos[tile] = DoorInfo(tile, orientation)

    def _place_sensors(self) -> None:
        count = max(3, min(8, len(self.open_tiles) // 110 + 2))
        blocked = set(self.doors) | set(self.cards) | {self.start, self.exit}
        candidates = [
            tile for tile in self.open_tiles
            if tile not in blocked
            and self._degree_raw(tile) == 2
            and self.dist_from_start.get(tile, 0) >= 5
            and min(manhattan(tile, t) for t in blocked) >= 2
        ]
        self.rng.shuffle(candidates)
        for tile in candidates:
            if len(self.sensors) >= count:
                break
            if min((manhattan(tile, s) for s in self.sensors), default=99) < 3:
                continue
            self.sensors.add(tile)

    def _place_hazards(self) -> None:
        count = max(4, min(14, len(self.open_tiles) // 85))
        blocked = (
            set(self.doors) | set(self.sensors) | set(self.cards)
            | {self.start, self.exit}
        )
        candidates = [
            tile for tile in self.open_tiles
            if tile not in blocked
            and self._degree_raw(tile) >= 2
            and self.dist_from_start.get(tile, 0) >= 3
            and min(manhattan(tile, t) for t in blocked) >= 2
        ]
        self.rng.shuffle(candidates)
        for tile in candidates:
            if len(self.hazards) >= count:
                break
            if min((manhattan(tile, h) for h in self.hazards), default=99) < 2:
                continue
            self.hazards.add(tile)
            # Pequeña zona de vapor alrededor de un cruce.
            for nxt in self._neighbors_open(tile):
                if len(self.hazards) >= count:
                    break
                if nxt in blocked or nxt in self.hazards:
                    continue
                if self.rng.random() < 0.35:
                    self.hazards.add(nxt)

    def _place_terminals(self) -> None:
        count = 2 if len(self.open_tiles) >= 120 else 1
        blocked = (
            set(self.doors) | set(self.sensors) | set(self.hazards)
            | set(self.cards) | {self.start, self.exit}
        )
        candidates = [
            tile for tile in self.open_tiles
            if tile not in blocked
            and self._degree_raw(tile) >= 2
            and self.dist_from_start.get(tile, 0) >= 5
            and min(manhattan(tile, t) for t in blocked) >= 2
        ]
        self.rng.shuffle(candidates)
        for tile in candidates:
            if len(self.terminals) >= count:
                break
            if min((manhattan(tile, t) for t in self.terminals), default=99) < 6:
                continue
            self.terminals.add(tile)

        if not self.terminals and candidates:
            self.terminals.add(candidates[0])

    def _place_agents_and_patrols(self) -> None:
        blocked = (
            set(self.doors) | set(self.sensors) | set(self.hazards)
            | set(self.terminals) | set(self.cards) | {self.start, self.exit}
        )
        candidates = [
            t for t in self.open_tiles
            if t not in blocked and self._degree_raw(t) >= 2
            and self.dist_from_start.get(t, 0) >= 4
        ]
        if not candidates:
            candidates = [t for t in self.open_tiles if t != self.start]

        # Puntos de patrulla por muestreo del punto más lejano.
        selected: list[Coord] = []
        pool = list(candidates)
        # Primer punto: lo más lejos posible del jugador.
        first = max(pool, key=lambda t: (self.dist_from_start.get(t, 0), self.rng.random()))
        selected.append(first)
        for _ in range(3):
            if not pool:
                break
            best = max(
                (t for t in pool if t not in selected),
                key=lambda t: (min(manhattan(t, s) for s in selected), self.rng.random()),
                default=None,
            )
            if best is None:
                break
            selected.append(best)
        while len(selected) < 4:
            selected.append(self.rng.choice(candidates))
        self.patrol_points: list[Coord] = selected[:4]

        # ARGOS aparece a media distancia, lejos del jugador y de las tarjetas.
        max_dist = max(self.dist_from_start.values(), default=0)
        argos_candidates = [
            t for t in candidates
            if self.dist_from_start.get(t, 0) >= max(9, max_dist // 3)
            and min(manhattan(t, card) for card in self.cards) >= 7
        ]
        if not argos_candidates:
            argos_candidates = [
                t for t in candidates
                if self.dist_from_start.get(t, 0) >= max(7, max_dist // 4)
            ]
        self.argos_start = self.rng.choice(argos_candidates or candidates)

        # Drones: dos rutas de patrulla por sectores.
        self.drone_routes: list[list[Coord]] = []
        for index in range(config.DRONE_COUNT):
            a = self.patrol_points[index % len(self.patrol_points)]
            b = self.patrol_points[(index + 2) % len(self.patrol_points)]
            self.drone_routes.append([a, b])
        self.drone_starts: list[Coord] = []
        for route in self.drone_routes:
            start = route[0]
            if start == self.start:
                start = self.patrol_points[-1]
            self.drone_starts.append(start)

    # ------------------------------------------------------------------
    # Costes y grafo
    # ------------------------------------------------------------------
    def _ensure_route_door(self) -> None:
        """Garantiza una puerta bloqueable en la ruta inicial hacia una tarjeta."""
        graph = GridGraph(self.open_tiles, self.costs)
        route = dijkstra(graph, self.start, set(self.cards) or {self.exit})
        if not route.found:
            return

        def has_useful_detour(tile: Coord) -> bool:
            if not self._door_has_alternative(tile):
                return False
            graph.set_blocked(tile, True)
            try:
                alternative = dijkstra(graph, self.start, {route.goal})
            finally:
                graph.set_blocked(tile, False)
            return (
                alternative.found
                and alternative.cost > route.cost + 1e-9
                and alternative.cost <= max(route.cost * 4.0, route.cost + 80.0)
            )

        for tile in route.path[1:-1]:
            if tile in self.doors:
                if has_useful_detour(tile):
                    return
                continue
            if tile in self.important_tiles or self._door_orientation_raw(tile) is None:
                continue
            if not has_useful_detour(tile):
                continue
            self.sensors.discard(tile)
            self.hazards.discard(tile)
            self.terminals.discard(tile)
            orientation = self._door_orientation_raw(tile)
            self.doors.add(tile)
            self.door_infos[tile] = DoorInfo(tile, orientation or "horizontal")
            self.costs[tile] = config.DOOR_COST
            return

    def _build_costs_and_graph(self) -> None:
        self.costs: dict[Coord, float] = {tile: config.FLOOR_COST for tile in self.open_tiles}
        for tile in self.sensors:
            self.costs[tile] = config.SENSOR_COST
        for tile in self.hazards:
            self.costs[tile] = config.HAZARD_COST
        for tile in self.doors:
            self.costs[tile] = config.DOOR_COST
        self._ensure_route_door()
        self.graph = GridGraph(self.open_tiles, self.costs)
        # Verificación de jugabilidad.
        reachable = self.graph.reachable(self.start)
        needed = {self.exit, *self.cards}
        if not needed.issubset(reachable):
            raise RuntimeError(
                f"mapa inviable (semilla {self.seed}): objetivos inalcanzables"
            )

    # ------------------------------------------------------------------
    # Consultas / estado dinámico
    # ------------------------------------------------------------------
    def can_enter(self, tile: Coord) -> bool:
        return self.graph.is_open(tile)

    def degree(self, tile: Coord) -> int:
        return sum(1 for _ in self.graph.neighbors(tile))

    def door_orientation(self, tile: Coord) -> str:
        info = self.door_infos.get(tile)
        return info.orientation if info else "horizontal"

    def is_door(self, tile: Coord) -> bool:
        return tile in self.doors

    def is_locked(self, tile: Coord) -> bool:
        return tile in self.locked_doors

    def lock_door(self, tile: Coord, now: float, duration: float) -> bool:
        if tile not in self.doors or tile in self.locked_doors:
            return False
        self.locked_doors[tile] = now + duration
        self.graph.set_blocked(tile, True)
        return True

    def unlock_door(self, tile: Coord) -> bool:
        if tile not in self.locked_doors:
            return False
        del self.locked_doors[tile]
        self.graph.set_blocked(tile, False)
        return True

    def unlock_expired(self, now: float) -> list[Coord]:
        expired = [tile for tile, until in self.locked_doors.items() if until <= now]
        for tile in expired:
            self.unlock_door(tile)
        return expired

    def unlock_all_doors(self) -> list[Coord]:
        unlocked = list(self.locked_doors)
        for tile in unlocked:
            self.unlock_door(tile)
        return unlocked

    def targets_reachable_without(self, blocked_tile: Coord,
                                  start: Coord | None = None,
                                  targets: Iterable[Coord] | None = None) -> bool:
        start = start if start is not None else self.start
        targets = set(targets) if targets is not None else set(self.important_tiles)
        reachable = self.graph.reachable(start, extra_blocked={blocked_tile})
        return targets.issubset(reachable)

    @property
    def size_label(self) -> str:
        return f"{self.width}x{self.height} baldosas"

    def linear_index(self, tile: Coord) -> int:
        return tile[1] * self.width + tile[0]
