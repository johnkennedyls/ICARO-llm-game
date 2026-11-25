"""Agentes autónomos de El escape de Ícaro.

Ciclo de cada agente:
percepción → memoria/contexto → planificación → decisión → ejecución →
evaluación → actualización del entorno/memoria.

Ambos algoritmos se ejecutan sobre el mismo objetivo en cada replanificación
para alimentar la comparación del panel. El agente sigue el elegido
globalmente con F1.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field

from . import config
from .algorithms import SearchResult, astar, dijkstra
from .graph import Coord, manhattan
from .planning import PredictionResult, predict_intercept


def fmt(tile: Coord | None) -> str:
    return "—" if tile is None else f"({tile[0]},{tile[1]})"


@dataclass
class AgentMemory:
    sightings: int = 0
    reports: int = 0
    plan_changes: int = 0
    replans: int = 0
    blocked_corridors: int = 0
    prediction_checks: int = 0
    prediction_hits: int = 0
    notes: deque[str] = field(default_factory=lambda: deque(maxlen=8))


class Entity:
    def __init__(self, name: str, tile: Coord, step_time: float, color: tuple[int, int, int]):
        self.name = name
        self.tile: Coord = tile
        self.spawn: Coord = tile
        self.visual: list[float] = [float(tile[0]), float(tile[1])]
        self.facing: Coord = (0, 1)
        self.step_time = step_time
        self.step_timer = 0.0
        self.color = color
        self.steps = 0

    def update_visual(self, dt: float) -> None:
        k = min(1.0, dt * 15.0)
        self.visual[0] += (self.tile[0] - self.visual[0]) * k
        self.visual[1] += (self.tile[1] - self.visual[1]) * k


class PlanningAgent(Entity):
    """Base para agentes que planifican con Dijkstra/A*."""

    def __init__(self, name: str, tile: Coord, step_time: float,
                 color: tuple[int, int, int], role: str):
        super().__init__(name, tile, step_time, color)
        self.role = role
        self.state = "INACTIVO"
        self.path: list[Coord] = []
        self.goal: Coord | None = None
        self.target_label = "—"
        self.last_dijkstra: SearchResult | None = None
        self.last_astar: SearchResult | None = None
        self.last_search: SearchResult | None = None
        self.plans = 0
        self.memory = AgentMemory()
        self.last_plan_at = -999.0
        self.next_plan_at = 0.0
        self.think_timer = 0.0
        self.planned_state = ""

    # -- planificación -----------------------------------------------------
    def plan_to(self, game, targets, *, remember: bool = True) -> SearchResult | None:
        targets = {t for t in targets if game.maze.can_enter(t)}
        if not targets:
            self.path = []
            self.goal = None
            return None

        graph = game.maze.graph
        if len(targets) > 1:
            selector = dijkstra(graph, self.tile, targets)
            if not selector.found:
                self.path = []
                self.goal = None
                self.last_dijkstra = selector
                self.last_astar = astar(graph, self.tile, targets)
                self.last_search = selector
                game.register_search(self, selector, self.last_astar)
                return selector
            target = selector.goal
        else:
            target = next(iter(targets))

        d_res = dijkstra(graph, self.tile, target)
        a_res = astar(graph, self.tile, target)
        chosen = a_res if game.algorithm == config.ALGO_ASTAR else d_res
        self.last_dijkstra = d_res
        self.last_astar = a_res
        self.last_search = chosen
        self.plans += 1
        self.last_plan_at = game.time
        if chosen.found:
            self.path = list(chosen.path[1:])
            self.goal = chosen.goal
        else:
            self.path = []
            self.goal = None
        game.register_search(self, d_res, a_res)
        return chosen

    def path_blocked(self, game) -> bool:
        return bool(self.path) and not game.maze.can_enter(self.path[0])

    def advance(self, game) -> bool:
        if not self.path:
            return False
        nxt = self.path[0]
        if not game.maze.can_enter(nxt):
            self.path.clear()
            return False
        self.path.pop(0)
        self.facing = (nxt[0] - self.tile[0], nxt[1] - self.tile[1])
        self.tile = nxt
        self.steps += 1
        return True

    # -- métricas ----------------------------------------------------------
    @property
    def expanded_last(self) -> int:
        return self.last_search.expanded if self.last_search else 0

    @property
    def cost_last(self) -> float:
        return self.last_search.cost if self.last_search and self.last_search.found else float("nan")

    @property
    def ms_last(self) -> float:
        return self.last_search.elapsed_ms if self.last_search else 0.0

    def algorithm_used(self) -> str:
        if self.last_search:
            return config.ALGO_LABEL.get(self.last_search.algorithm, self.last_search.algorithm)
        return config.ALGO_LABEL[config.ALGO_ASTAR]


class Argos(PlanningAgent):
    """Cazador central: patrulla, investiga, intercepta y bloquea puertas."""

    def __init__(self, maze):
        super().__init__("ARGOS", maze.argos_start, config.ARGOS_STEP_TIME,
                         config.COL_RED, "Cazador autónomo")
        self.state = "PATRULLA"
        self.patrol_points = list(maze.patrol_points)
        self.patrol_index = 0
        self.player_visible = False
        self.last_seen: Coord | None = None
        self.last_seen_at = -999.0
        self.pending_prediction: Coord | None = None
        self.prediction: PredictionResult | None = None
        self.heat: Counter[Coord] = Counter()
        self.crossings: set[Coord] = set()
        self.lock_ready_at = config.ARGOS_LOCK_AFTER
        self.target_label = "Patrulla"
        self.was_visible = False
        self.security_gained = 0.0
        self.last_plan_log_at = -999.0
        self.last_fail_log_at = -999.0

    # -- percepción --------------------------------------------------------
    def sees_player(self, game) -> bool:
        p = game.player.tile
        if manhattan(self.tile, p) > config.ARGOS_VISION:
            return False
        if config.ARGOS_VISION >= 99:
            return True
        return game.maze.graph.line_of_sight(self.tile, p)

    def receive_report(self, game, sender: str, position: Coord) -> None:
        self.last_seen = position
        self.last_seen_at = game.time
        self.heat[position] += 2
        self.memory.notes.append(f"{sender}: objetivo en {fmt(position)}")
        game.log_event(
            "ARGOS", f"recibe reporte de {sender}: Ícaro en {fmt(position)}", "mensaje"
        )

    def notify_sensor(self, game, position: Coord) -> None:
        self.last_seen = position
        self.last_seen_at = game.time
        self.heat[position] += 1
        self.memory.notes.append(f"Sensor: {fmt(position)}")

    # -- ciclo -------------------------------------------------------------
    def update(self, game, dt: float) -> None:
        self.update_visual(dt)
        self.think_timer -= dt
        if self.think_timer <= 0.0:
            self.think(game)
            self.think_timer = config.ARGOS_THINK_TIME * (
                1.0 - 0.25 * min(game.security, config.SECURITY_MAX) / config.SECURITY_MAX
            )
        self.step_timer -= dt
        if self.step_timer <= 0.0 and self.path:
            if self.advance(game):
                speed_factor = 1.0 + 0.30 * min(game.security, 100.0) / 100.0
                interval = max(config.ARGOS_STEP_MIN, self.step_time / speed_factor)
                self.step_timer = interval
            else:
                self.step_timer = 0.05

    def think(self, game) -> None:
        now = game.time
        visible = self.sees_player(game)
        self.player_visible = visible
        blocked_before = self.path_blocked(game)

        if visible:
            if not self.was_visible:
                game.log_event(
                    "ARGOS",
                    f"avistamiento de Ícaro en {fmt(game.player.tile)} a {manhattan(self.tile, game.player.tile)} baldosas",
                    "percepcion",
                )
            self.was_visible = True
            self.last_seen = game.player.tile
            self.last_seen_at = now
            self.memory.sightings += 1
            is_crossing = game.maze.degree(game.player.tile) >= 3
            self.heat[game.player.tile] += 2 if is_crossing else 1
            if is_crossing:
                self.crossings.add(game.player.tile)

            # Evaluación del pronóstico anterior.
            if self.pending_prediction is not None:
                self.memory.prediction_checks += 1
                if manhattan(game.player.tile, self.pending_prediction) <= 1:
                    self.memory.prediction_hits += 1
                self.pending_prediction = None

            objectives = game.player_objectives()
            self.prediction = predict_intercept(
                game.maze,
                self.tile,
                game.player.tile,
                objectives,
                self.heat,
            )
            target = self.prediction.target or game.player.tile
            if target != game.player.tile:
                self.state = "INTERCEPTA"
                self.target_label = f"Interceptar en {fmt(target)}"
            else:
                self.state = "CAZA"
                self.target_label = f"Perseguir a Ícaro {fmt(target)}"
            self.pending_prediction = self.prediction.probable
        else:
            if self.was_visible:
                game.log_event(
                    "ARGOS",
                    f"pierde contacto visual; última posición {fmt(self.last_seen)}",
                    "percepcion",
                )
            self.was_visible = False
            age = now - self.last_seen_at
            if self.last_seen is not None and age <= config.ARGOS_MEMORY_TTL:
                self.state = "INVESTIGA"
                target = self.last_seen
                self.target_label = f"Investigar última posición {fmt(target)}"
                if self.tile == self.last_seen and age > 2.2:
                    game.log_event(
                        "ARGOS", f"sin rastro en {fmt(self.last_seen)}; vuelve a patrullar", "memoria"
                    )
                    self.last_seen = None
                    self.state = "PATRULLA"
                    target = self._next_patrol_target()
                    self.target_label = f"Patrulla {fmt(target)}"
            else:
                if self.last_seen is not None:
                    game.log_event(
                        "ARGOS",
                        f"memoria de {fmt(self.last_seen)} expirada; reanuda patrulla",
                        "memoria",
                    )
                    self.last_seen = None
                self.state = "PATRULLA"
                target = self._next_patrol_target()
                self.target_label = f"Patrulla {fmt(target)}"
                self.prediction = None

        target_changed = self.goal != target
        state_changed = self.planned_state != self.state
        needs_plan = (
            target_changed
            or state_changed
            or not self.path
            or blocked_before
            or now >= self.next_plan_at
        )
        if needs_plan:
            chosen = self.plan_to(game, {target})
            if (chosen is None or not chosen.found) and self.state in ("CAZA", "INTERCEPTA", "INVESTIGA"):
                # La meta táctica no es alcanzable: repliega a patrulla.
                fallback = self.plan_to(game, set(self.patrol_points))
                if fallback is not None and fallback.found:
                    self.state = "PATRULLA"
                    self.target_label = f"Patrulla (repliegue) {fmt(self.goal)}"
                    game.log_event(
                        "ARGOS",
                        f"objetivo inalcanzable; repliega a {fmt(self.goal)}",
                        "replan",
                    )
                chosen = fallback

            self.planned_state = self.state
            intervals = {"CAZA": 0.36, "INTERCEPTA": 0.46, "INVESTIGA": 0.72, "PATRULLA": 1.1}
            self.next_plan_at = now + intervals.get(self.state, 0.7)

            if chosen is not None and chosen.found:
                if target_changed or state_changed:
                    self.memory.plan_changes += 1
                    if now - self.last_plan_log_at >= 1.1 or state_changed:
                        self.last_plan_log_at = now
                        game.log_event(
                            "ARGOS",
                            f"{self.state} → {fmt(self.goal)} · {chosen.algorithm_label} · "
                            f"coste {chosen.cost:g} · {chosen.expanded} expandidos · {chosen.elapsed_ms:.2f} ms",
                            "plan",
                        )
                elif blocked_before:
                    self.memory.replans += 1
                    game.log_event(
                        "ARGOS",
                        f"ruta bloqueada; replanifica a {fmt(self.goal)} · "
                        f"{chosen.algorithm_label} · coste {chosen.cost:g}",
                        "replan",
                    )
            else:
                self.path = []
                if now - self.last_fail_log_at > 3.0:
                    self.last_fail_log_at = now
                    game.log_event(
                        "ARGOS", "no encuentra ruta a ningún punto de patrulla", "error"
                    )

        # Acción especial: bloquear un corredor de la ruta de Ícaro.
        recently_seen = now - self.last_seen_at <= 6.0
        if (
            (visible or recently_seen)
            and now >= self.lock_ready_at
            and game.security >= 12.0
        ):
            result = game.try_blockade("ARGOS", by_argos=True)
            cooldown = config.ARGOS_LOCK_COOLDOWN * (
                1.0 - 0.25 * min(game.security, 100.0) / 100.0
            )
            self.lock_ready_at = now + cooldown
            if result:
                self.memory.blocked_corridors += 1

    def _next_patrol_target(self) -> Coord:
        if not self.patrol_points:
            return self.tile
        if self.tile == self.patrol_points[self.patrol_index % len(self.patrol_points)]:
            self.patrol_index = (self.patrol_index + 1) % len(self.patrol_points)
        return self.patrol_points[self.patrol_index % len(self.patrol_points)]

    # -- panel -------------------------------------------------------------
    def perception_text(self, game) -> str:
        dist = manhattan(self.tile, game.player.tile)
        if self.player_visible:
            return f"Ícaro visible a {dist} baldosas"
        age = game.time - self.last_seen_at
        if self.last_seen is not None and age <= config.ARGOS_MEMORY_TTL:
            return f"sin contacto; recuerdo hace {age:.1f}s en {fmt(self.last_seen)}"
        return "sin contacto; patrulla el sector"

    def memory_text(self, game) -> str:
        crossings = len(self.crossings)
        hits = self.memory.prediction_hits
        checks = self.memory.prediction_checks
        accuracy = f"{100 * hits / checks:.0f}%" if checks else "—"
        return (
            f"avistamientos {self.memory.sightings} · cruces memorizados {crossings} · "
            f"aciertos {hits}/{checks} ({accuracy})"
        )


class Drone(PlanningAgent):
    """Explorador de sector: informa posiciones a ARGOS."""

    def __init__(self, maze, index: int):
        route = list(maze.drone_routes[index % len(maze.drone_routes)])
        start = maze.drone_starts[index % len(maze.drone_starts)]
        super().__init__(f"Dron-{index + 1}", start, config.DRONE_STEP_TIME + 0.02 * index,
                         config.COL_CYAN if index == 0 else config.COL_PURPLE,
                         "Explorador / comunicaciones")
        self.route = route
        self.route_index = 0
        self.state = "PATRULLA"
        self.target_label = f"Patrulla {fmt(route[0])}"
        self.player_visible = False
        self.last_report_at = -999.0
        self.last_seen: Coord | None = None
        self.reports = 0
        self.think_timer = 0.1 * index
        self.step_timer = 0.2 + 0.05 * index
        self.next_plan_at = 0.0

    def update(self, game, dt: float) -> None:
        self.update_visual(dt)
        self.think_timer -= dt
        if self.think_timer <= 0.0:
            self.think(game)
            self.think_timer = config.DRONE_THINK_TIME
        self.step_timer -= dt
        if self.step_timer <= 0.0 and self.path:
            if self.advance(game):
                self.step_timer = self.step_time
            else:
                self.step_timer = 0.08

    def think(self, game) -> None:
        now = game.time
        visible = (
            manhattan(self.tile, game.player.tile) <= config.DRONE_VISION
            and game.maze.graph.line_of_sight(self.tile, game.player.tile)
        )
        self.player_visible = visible
        blocked_before = self.path_blocked(game)
        if visible:
            self.state = "AVISTAMIENTO"
            self.last_seen = game.player.tile
            self.target_label = f"Ícaro detectado {fmt(game.player.tile)}"
            if now - self.last_report_at >= config.DRONE_REPORT_COOLDOWN:
                self.last_report_at = now
                game.drone_report(self, game.player.tile)
        else:
            self.state = "PATRULLA"
            if self.player_visible is False and now - self.last_report_at < 2.0:
                self.state = "ALERTA"
                self.target_label = f"Barrido de {fmt(self.last_seen)}"
            else:
                self.target_label = f"Patrulla {fmt(self.route[self.route_index])}"

        waypoint = self.route[self.route_index % len(self.route)]
        if self.tile == waypoint:
            self.route_index = (self.route_index + 1) % len(self.route)
            waypoint = self.route[self.route_index % len(self.route)]
            self.target_label = f"Patrulla {fmt(waypoint)}"

        needs_plan = (
            not self.path
            or blocked_before
            or self.goal != waypoint
            or now >= self.next_plan_at
        )
        if needs_plan:
            chosen = self.plan_to(game, {waypoint})
            self.next_plan_at = now + 1.15
            if chosen is not None and chosen.found and blocked_before:
                game.log_event(
                    self.name,
                    f"ruta bloqueada; replanifica a {fmt(waypoint)} · {chosen.algorithm_label}",
                    "replan",
                )

    def perception_text(self, game) -> str:
        if self.player_visible:
            return f"Ícaro a la vista ({manhattan(self.tile, game.player.tile)} baldosas)"
        if self.last_seen is not None:
            return f"sector despejado; último avistamiento {fmt(self.last_seen)}"
        return "sector despejado"

    def memory_text(self, game) -> str:
        return f"reportes enviados {self.reports} · sector {self.route[self.route_index]}"

    def receive_report(self, *args, **kwargs) -> None:  # paridad de interfaz
        return


class PlayerBot:
    """Piloto automático de Ícaro: recoge tarjetas y escapa."""

    def __init__(self, name: str = "Piloto IA"):
        self.name = name
        self.state = "EN ESPERA"
        self.target_label = "—"
        self.path: list[Coord] = []
        self.goal: Coord | None = None
        self.last_dijkstra: SearchResult | None = None
        self.last_astar: SearchResult | None = None
        self.last_search: SearchResult | None = None
        self.plans = 0
        self.replans = 0
        self.think_timer = 0.0
        self.last_plan_at = -999.0
        self.last_objectives: set[Coord] = set()
        self.plan_changes = 0

    # La interfaz de panel comparte campos con PlanningAgent.
    @property
    def algorithm_used(self) -> str:
        if self.last_search:
            return config.ALGO_LABEL.get(self.last_search.algorithm, self.last_search.algorithm)
        return config.ALGO_LABEL[config.ALGO_ASTAR]

    @property
    def expanded_last(self) -> int:
        return self.last_search.expanded if self.last_search else 0

    @property
    def cost_last(self) -> float:
        return self.last_search.cost if self.last_search and self.last_search.found else float("nan")

    @property
    def ms_last(self) -> float:
        return self.last_search.elapsed_ms if self.last_search else 0.0

    def plan(self, game, *, reason: str = "", announce: bool = False) -> SearchResult | None:
        objectives = game.player_objectives()
        if not objectives:
            self.path = []
            self.goal = None
            self.state = "SIN OBJETIVO"
            return None
        self.last_objectives = set(objectives)
        graph = game.maze.graph
        risk = self._risk_bias(game)
        selector = dijkstra(graph, game.player.tile, objectives, cost_bias=risk)
        if not selector.found:
            self.path = []
            self.last_dijkstra = selector
            self.last_astar = astar(graph, game.player.tile, objectives, cost_bias=risk)
            return selector
        target = selector.goal
        d_res = dijkstra(graph, game.player.tile, target, cost_bias=risk)
        a_res = astar(graph, game.player.tile, target, cost_bias=risk)
        chosen = a_res if game.algorithm == config.ALGO_ASTAR else d_res
        self.last_dijkstra = d_res
        self.last_astar = a_res
        self.last_search = chosen
        self.plans += 1
        self.last_plan_at = game.time
        self.state = "EN RUTA"
        if chosen.found:
            self.path = list(chosen.path[1:])
            self.goal = chosen.goal
            if target == game.maze.exit:
                self.target_label = f"Salida {fmt(target)}"
            else:
                self.target_label = f"Tarjeta {fmt(target)}"
            self.plan_changes += 1
            if announce:
                game.log_event(
                    "PILOTO",
                    f"{('replanifica: ' + reason + ' · ') if reason else 'planifica · '}"
                    f"{chosen.algorithm_label} → {fmt(target)} · coste {chosen.cost:g} · "
                    f"{chosen.expanded} nodos · {chosen.elapsed_ms:.2f} ms",
                    "plan",
                )
        else:
            self.path = []
            self.goal = None
            self.state = "SIN RUTA"
            game.log_event("PILOTO", "no encuentra ruta hacia sus objetivos", "error")
        game.register_search(self, d_res, a_res)
        return chosen

    def _risk_bias(self, game) -> dict[Coord, float]:
        """Penaliza acercarse a ARGOS y a su intercepción prevista."""
        bias: dict[Coord, float] = {}
        argos = game.argos
        ax, ay = argos.tile
        scale = 1.0 if argos.player_visible or game.time - argos.last_seen_at < 5.0 else 0.65
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                dist = abs(dx) + abs(dy)
                if dist > 4:
                    continue
                penalty = {0: 999.0, 1: 60.0, 2: 32.0, 3: 12.0, 4: 3.0}[dist]
                bias[(ax + dx, ay + dy)] = max(
                    bias.get((ax + dx, ay + dy), 0.0), penalty * scale
                )
        prediction = argos.prediction
        if prediction is not None and prediction.target is not None:
            px, py = prediction.target
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    tile = (px + dx, py + dy)
                    bias[tile] = max(bias.get(tile, 0.0), 16.0)
        return bias

    def update(self, game, dt: float) -> None:
        if not game.autopilot or game.state != "playing":
            return
        self.think_timer -= dt
        if self.think_timer <= 0.0:
            self.think_timer = 0.25
            objectives = game.player_objectives()
            targets_changed = objectives != self.last_objectives
            blocked = bool(self.path) and not game.maze.can_enter(self.path[0])
            if blocked:
                self.replans += 1
            due = game.time > self.next_replan_at()
            if (
                blocked
                or not self.path
                or targets_changed
                or self.last_search is None
                or due
            ):
                reason = "corredor bloqueado" if blocked else ""
                announce = blocked or targets_changed or self.last_search is None
                self.plan(game, reason=reason, announce=announce)

        if game.player.step_timer <= 0.0 and self.path:
            nxt = self.path[0]
            if nxt == game.argos.tile:
                # No caminar directamente hacia el cazador.
                self.path.clear()
                return
            direction = (nxt[0] - game.player.tile[0], nxt[1] - game.player.tile[1])
            if abs(direction[0]) + abs(direction[1]) == 1:
                if game.attempt_player_move(direction):
                    self.path.pop(0)
                else:
                    self.path.clear()
            else:
                self.path.clear()

    def next_replan_at(self) -> float:
        return self.last_plan_at + 2.0

    def perception_text(self, game) -> str:
        return (
            f"tarjetas {len(game.player.cards)}/{config.CARD_COUNT} · "
            f"energía {game.player.energy:.0f} · piloto automático activo"
        )

    def memory_text(self, game) -> str:
        return (
            f"planes {self.plans} · replanificaciones por bloqueo {self.replans} · "
            f"objetivo {fmt(self.goal)}"
        )


class Player(Entity):
    def __init__(self, maze):
        super().__init__("Ícaro", maze.start, config.PLAYER_STEP_TIME,
                         config.COL_GREEN)
        self.energy = config.ENERGY_MAX
        self.cards: set[Coord] = set()
        self.step_timer = 0.0
        self.autopilot = False

    @property
    def cards_collected(self) -> int:
        return len(self.cards)
