"""Grafo ponderado del laberinto.

Modelo
-----
* Vértice: cada baldosa transitable del laberinto ``(x, y)``.
* Arista: conexión ortogonal entre dos vértices transitables.
* Peso: coste de *entrar* a la baldosa destino:
  suelo = 1, sensor = 2, vapor = 3, puerta = 1.
  Una puerta cerrada se elimina temporalmente del grafo.

De este modo todos los pesos son no negativos (requisito de Dijkstra) y el
grafo puede cambiar en caliente cuando ARGOS bloquea una puerta.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator

Coord = tuple[int, int]

# Orden determinista de expansión: norte, este, sur, oeste.
NEIGHBOR_ORDER: tuple[Coord, ...] = ((0, -1), (1, 0), (0, 1), (-1, 0))


def manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def neighbors4(tile: Coord) -> Iterator[Coord]:
    x, y = tile
    for dx, dy in NEIGHBOR_ORDER:
        yield x + dx, y + dy


def bresenham(a: Coord, b: Coord) -> Iterator[Coord]:
    """Línea discreta entre dos baldosas, ambos extremos incluidos."""
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


class GridGraph:
    """Grafo implícito sobre una rejilla ortogonal."""

    def __init__(
        self,
        open_tiles: Iterable[Coord],
        costs: dict[Coord, float],
        blocked: set[Coord] | None = None,
    ) -> None:
        self.open_tiles: set[Coord] = set(open_tiles)
        self.costs: dict[Coord, float] = dict(costs)
        self.blocked: set[Coord] = set(blocked or ())

    # -- consultas ---------------------------------------------------------
    def is_open(self, tile: Coord) -> bool:
        return tile in self.open_tiles and tile not in self.blocked

    def tile_cost(self, tile: Coord) -> float:
        return self.costs.get(tile, 1.0)

    def neighbors(self, tile: Coord) -> Iterator[tuple[Coord, float]]:
        """Vecinos transitables con el coste de entrar en ellos."""
        x, y = tile
        for dx, dy in NEIGHBOR_ORDER:
            nxt = (x + dx, y + dy)
            if nxt in self.open_tiles and nxt not in self.blocked:
                yield nxt, self.costs.get(nxt, 1.0)

    def set_blocked(self, tile: Coord, blocked: bool = True) -> None:
        if blocked:
            self.blocked.add(tile)
        else:
            self.blocked.discard(tile)

    # -- métricas ----------------------------------------------------------
    @property
    def vertices(self) -> int:
        return len(self.open_tiles - self.blocked)

    @property
    def edges(self) -> int:
        total = 0
        for tile in self.open_tiles - self.blocked:
            x, y = tile
            for dx, dy in ((1, 0), (0, 1)):
                other = (x + dx, y + dy)
                if other in self.open_tiles and other not in self.blocked:
                    total += 1
        return total

    def edge_cost(self, a: Coord, b: Coord) -> float:
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
            raise ValueError("las aristas solo conectan vecinos ortogonales")
        return self.tile_cost(b)

    # -- utilidades de navegación -----------------------------------------
    def reachable(self, start: Coord, extra_blocked: Iterable[Coord] = ()) -> set[Coord]:
        """Componente conexa alcanzable desde ``start`` (BFS, sin pesos)."""
        extra = set(extra_blocked)
        if not self.is_open(start) or start in extra:
            return set()
        seen = {start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            x, y = node
            for dx, dy in NEIGHBOR_ORDER:
                nxt = (x + dx, y + dy)
                if nxt in seen or nxt in extra or nxt in self.blocked:
                    continue
                if nxt in self.open_tiles:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def distance_map(
        self,
        start: Coord,
        extra_blocked: Iterable[Coord] = (),
    ) -> dict[Coord, int]:
        """Distancias topológicas (número de pasos) desde ``start``."""
        extra = set(extra_blocked)
        if not self.is_open(start) or start in extra:
            return {}
        dist = {start: 0}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            x, y = node
            for dx, dy in NEIGHBOR_ORDER:
                nxt = (x + dx, y + dy)
                if (
                    nxt in dist
                    or nxt in extra
                    or nxt in self.blocked
                    or nxt not in self.open_tiles
                ):
                    continue
                dist[nxt] = dist[node] + 1
                queue.append(nxt)
        return dist

    def line_of_sight(self, a: Coord, b: Coord) -> bool:
        """Visión sobre la rejilla; muros y puertas cerradas bloquean."""
        if a == b:
            return self.is_open(a)
        for index, tile in enumerate(bresenham(a, b)):
            if index == 0:
                continue
            if tile not in self.open_tiles or tile in self.blocked:
                # la propia baldosa destino puede ser un muro visible, pero
                # para IA solo se consulta contra agentes en suelo abierto.
                return False
        return True

    def visible_tiles(self, origin: Coord, radius: float) -> set[Coord]:
        """Baldosas (incluidos muros visibles) dentro del radio con LOS."""
        result: set[Coord] = set()
        r = int(radius + 0.999)
        ox, oy = origin
        for y in range(oy - r, oy + r + 1):
            for x in range(ox - r, ox + r + 1):
                tile = (x, y)
                if (x - ox) ** 2 + (y - oy) ** 2 > (radius + 0.5) ** 2:
                    continue
                if tile == origin:
                    result.add(tile)
                    continue
                blocked_before = False
                for index, step in enumerate(bresenham(origin, tile)):
                    if index == 0:
                        continue
                    if step in self.blocked:
                        blocked_before = True
                        break
                    if step != tile and step not in self.open_tiles:
                        blocked_before = True
                        break
                if not blocked_before:
                    result.add(tile)
        return result
