"""Estado completo de la partida, independiente de Pygame.

La capa gráfica (``render.py`` / ``app.py``) lee este estado y la capa de
entrada le envía acciones. Así la simulación se puede probar sin ventana.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import perf_counter

from . import config
from .agents import Argos, Drone, Player, PlayerBot, fmt
from .algorithms import dijkstra
from .graph import Coord, manhattan
from .maze import Maze
from .session_log import SessionLog
from .llm_agents import LLMConfig, initialize_llm_agents


@dataclass(slots=True)
class LogEntry:
    time: float
    speaker: str
    text: str
    category: str


class Game:
    def __init__(self, seed: int = config.DEFAULT_SEED,
                 cells_x: int = config.DEFAULT_CELLS_X,
                 cells_y: int = config.DEFAULT_CELLS_Y,
                 write_log: bool = True):
        self.seed = seed
        self.cells_x = cells_x
        self.cells_y = cells_y
        self.maze = Maze(cells_x=cells_x, cells_y=cells_y, seed=seed)
        self.time = 0.0
        self.state = "playing"          # playing | won | lost
        self.end_reason = ""
        self.end_time = 0.0

        self.player = Player(self.maze)
        self.argos = Argos(self.maze)
        self.drones = [Drone(self.maze, i) for i in range(config.DRONE_COUNT)]
        self.bot = PlayerBot()

        # Agentes LLM (opcional)
        llm_config = LLMConfig.from_env()
        self.operator, self.analyst = initialize_llm_agents(llm_config)
        if self.operator:
            self.operator.set_game_seed(seed)

        self.autopilot = False
        self.algorithm = config.ALGO_ASTAR
        self.show_paths = True
        self.fog_enabled = True
        self.panel_index = 0

        self.security = 0.0
        self.sensors_disabled_until = -1.0
        self.reveal_until = -1.0
        self.used_terminals: set[Coord] = set()
        self.sensor_cooldowns: dict[Coord, float] = {}
        self.exit_hint_at = -99.0
        self.door_hint_at = -99.0

        self.log: deque[LogEntry] = deque(maxlen=300)
        self.effects: list[dict] = []
        self.flash = 0.0
        self.flash_color = config.COL_RED
        self.acceptance_tests: list[dict] = []
        self.stats = {
            "alarms": 0,
            "blocks": 0,
            "hacks": 0,
            "cards": 0,
            "searches": 0,
            "drone_reports": 0,
        }
        self.search_stats = {
            config.ALGO_ASTAR: {"count": 0, "nodes": 0, "ms": 0.0, "peak": 0, "found": 0},
            config.ALGO_DIJKSTRA: {"count": 0, "nodes": 0, "ms": 0.0, "peak": 0, "found": 0},
        }
        self.recent_searches: deque[dict] = deque(maxlen=16)
        self.log_file = SessionLog(seed, self.maze.size_label) if write_log else None
        self._closed = False

        self.log_event(
            "SISTEMA",
            f"partida iniciada · semilla {seed} · {self.maze.size_label} · "
            f"{self.maze.graph.vertices} vértices · {self.maze.graph.edges} aristas",
            "sistema",
        )
        self.log_event(
            "SISTEMA",
            f"objetivo: recuperar {config.CARD_COUNT} tarjetas y alcanzar la compuerta; "
            "ARGOS y 2 drones en línea",
            "info",
        )

    # ------------------------------------------------------------------
    # Utilidades de log / efectos
    # ------------------------------------------------------------------
    def log_event(self, speaker: str, text: str, category: str = "info") -> None:
        entry = LogEntry(self.time, speaker, text, category)
        self.log.append(entry)
        if self.log_file:
            self.log_file.write(self.time, speaker, category, text)

    def add_ring(self, tile: Coord, color: tuple[int, int, int],
                 duration: float = 0.7, max_radius: float = 2.0) -> None:
        self.effects.append({
            "kind": "ring", "tile": tile, "color": color,
            "age": 0.0, "duration": duration, "max_radius": max_radius,
        })

    def add_text(self, tile: Coord, text: str, color: tuple[int, int, int],
                 duration: float = 1.3) -> None:
        self.effects.append({
            "kind": "text", "tile": tile, "text": text, "color": color,
            "age": 0.0, "duration": duration,
        })

    def set_flash(self, color: tuple[int, int, int], amount: float = 0.5) -> None:
        self.flash_color = color
        self.flash = max(self.flash, amount)

    def _update_effects(self, dt: float) -> None:
        for effect in self.effects:
            effect["age"] += dt
        self.effects = [e for e in self.effects if e["age"] < e["duration"]]
        self.flash = max(0.0, self.flash - dt * 2.1)

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    @property
    def remaining_cards(self) -> list[Coord]:
        return [card for card in self.maze.cards if card not in self.player.cards]

    @property
    def exit_active(self) -> bool:
        return len(self.player.cards) >= config.CARD_COUNT

    @property
    def sensors_active(self) -> bool:
        return self.time >= self.sensors_disabled_until

    @property
    def sensors_remaining(self) -> float:
        return max(0.0, self.sensors_disabled_until - self.time)

    @property
    def reveal_active(self) -> bool:
        return self.time < self.reveal_until

    def player_objectives(self) -> set[Coord]:
        cards = self.remaining_cards
        if cards:
            return set(cards)
        return {self.maze.exit}

    def all_agents(self):
        return [self.argos, *self.drones, self.bot]

    def panel_agent(self):
        return self.all_agents()[self.panel_index % 4]

    def nearest_terminal(self) -> Coord | None:
        options = [
            tile for tile in self.maze.terminals
            if tile not in self.used_terminals
            and manhattan(tile, self.player.tile) <= max(config.TERMINAL_RANGE, 1.0)
        ]
        if not options:
            return None
        return min(options, key=lambda tile: manhattan(tile, self.player.tile))

    # ------------------------------------------------------------------
    # Acciones de entrada
    # ------------------------------------------------------------------
    def toggle_autopilot(self) -> None:
        self.autopilot = not self.autopilot
        self.player.autopilot = self.autopilot
        if self.autopilot:
            self.bot.think_timer = 0.0
            self.bot.path.clear()
            self.bot.last_search = None
            self.bot.plan(self)
            self.log_event("PILOTO", "piloto automático activado", "sistema")
        else:
            self.log_event("PILOTO", "control manual activado", "sistema")

    def toggle_algorithm(self) -> None:
        self.algorithm = (
            config.ALGO_DIJKSTRA if self.algorithm == config.ALGO_ASTAR
            else config.ALGO_ASTAR
        )
        now = self.time
        for agent in (self.argos, *self.drones):
            agent.next_plan_at = now
        if self.autopilot:
            self.bot.last_search = None
            self.bot.think_timer = 0.0
        label = config.ALGO_LABEL[self.algorithm]
        heuristic = "h Manhattan" if self.algorithm == config.ALGO_ASTAR else "sin heurística"
        self.log_event("SISTEMA", f"algoritmo de planificación → {label} ({heuristic})", "sistema")

    def cycle_panel(self, delta: int = 1) -> None:
        self.panel_index = (self.panel_index + delta) % 4

    def select_panel(self, index: int) -> None:
        self.panel_index = max(0, min(3, index))

    def force_blockade(self) -> dict | None:
        result = self.try_blockade("PRUEBA F5", by_argos=False)
        if result:
            self.log_event(
                "ACEPTACIÓN",
                f"✔ corredor bloqueado en {fmt(result['door'])}: "
                f"coste {result['before']:.0f} → {result['after']:.0f}; "
                "ruta alternativa verificada",
                "aceptacion",
            )
        return result

    def trigger_demo_alarm(self) -> None:
        self.raise_alarm(self.player.tile, "DEMO")

    def hack_terminal(self) -> bool:
        terminal = self.nearest_terminal()
        if terminal is None:
            self.log_event("SISTEMA", "no hay terminal sin usar al alcance", "info")
            return False
        if self.player.energy <= config.TERMINAL_ENERGY_COST:
            self.log_event("SISTEMA", "energía insuficiente para hackear", "error")
            return False
        self.used_terminals.add(terminal)
        self.player.energy -= config.TERMINAL_ENERGY_COST
        unlocked = self.maze.unlock_all_doors()
        self.sensors_disabled_until = self.time + config.SENSORS_DISABLED_TIME
        self.reveal_until = self.time + config.REVEAL_TIME
        self.security = max(0.0, self.security - 25.0)
        self.stats["hacks"] += 1
        self.add_ring(terminal, config.COL_CYAN, 1.0, 3.0)
        self.add_text(terminal, "ACCESO CONCEDIDO", config.COL_CYAN)
        self.set_flash(config.COL_CYAN, 0.25)
        detail = f", {len(unlocked)} puerta(s) liberada(s)" if unlocked else ""
        self.log_event(
            "SISTEMA",
            f"terminal {fmt(terminal)} hackeada: sensores inhabilitados "
            f"{config.SENSORS_DISABLED_TIME:.0f}s, ARGOS visible {config.REVEAL_TIME:.0f}s{detail}",
            "hack",
        )
        return True

    # ------------------------------------------------------------------
    # Movimiento del jugador
    # ------------------------------------------------------------------
    def attempt_player_move(self, direction: Coord) -> bool:
        if self.state != "playing":
            return False
        if self.player.energy <= 0.0:
            self.player.energy = 0.0
            self._lose("La energía del traje se ha agotado")
            return False
        if abs(direction[0]) + abs(direction[1]) != 1:
            return False
        if self.player.step_timer > 0.0:
            return False
        target = (self.player.tile[0] + direction[0], self.player.tile[1] + direction[1])
        if not self.maze.can_enter(target):
            if self.maze.is_door(target) and target in self.maze.locked_doors:
                if self.time - self.door_hint_at > 2.5:
                    self.door_hint_at = self.time
                    self.add_text(target, "PUERTA BLOQUEADA", config.COL_RED)
                    self.set_flash(config.COL_RED, 0.18)
            return False

        self.player.tile = target
        self.player.facing = direction
        self.player.steps += 1
        self.player.step_timer = config.PLAYER_STEP_TIME

        if target in self.maze.sensors:
            self._trigger_sensor(target)
        if target in self.maze.hazards:
            self.player.energy = max(0.0, self.player.energy - config.HAZARD_ENERGY_PENALTY)
            self.add_text(target, f"-{config.HAZARD_ENERGY_PENALTY:.0f} ENERGÍA", config.COL_AMBER, 0.9)
            if self.player.energy <= 0.0:
                self._lose("La energía del traje se ha agotado")
                return True
        if target in self.maze.cards and target not in self.player.cards:
            self._collect_card(target)
        if target == self.maze.exit:
            if self.exit_active:
                self._win()
            elif self.time - self.exit_hint_at > 3.0:
                self.exit_hint_at = self.time
                self.add_text(target, "FALTAN TARJETAS", config.COL_RED)
                self.log_event("SISTEMA", "la compuerta requiere las 3 tarjetas", "info")
        return True

    def _collect_card(self, tile: Coord) -> None:
        self.player.cards.add(tile)
        self.stats["cards"] += 1
        self.security = min(config.SECURITY_MAX, self.security + config.CARD_SECURITY)
        self.add_ring(tile, config.COL_CYAN, 0.9, 2.8)
        self.add_text(tile, f"TARJETA {len(self.player.cards)}/{config.CARD_COUNT}", config.COL_CYAN)
        self.log_event(
            "ÍCARO",
            f"recoge tarjeta {fmt(tile)} ({len(self.player.cards)}/{config.CARD_COUNT})",
            "logro",
        )
        if self.exit_active:
            self.add_ring(self.maze.exit, config.COL_GREEN, 1.2, 3.5)
            self.log_event(
                "SISTEMA",
                f"compuerta de salida activa en {fmt(self.maze.exit)} · ¡corre!",
                "logro",
            )
            self.argos.memory.notes.append("compuerta activa")
            self.security = min(config.SECURITY_MAX, self.security + 12.0)

    def _trigger_sensor(self, tile: Coord) -> None:
        if not self.sensors_active:
            return
        last = self.sensor_cooldowns.get(tile, -999.0)
        if self.time - last < 2.5:
            return
        self.sensor_cooldowns[tile] = self.time
        self.security = min(config.SECURITY_MAX, self.security + config.SENSOR_SECURITY)
        self.stats["alarms"] += 1
        self.add_ring(tile, config.COL_PURPLE, 1.0, 3.0)
        self.add_text(tile, "ALARMA", config.COL_PURPLE)
        self.set_flash(config.COL_PURPLE, 0.4)
        self.log_event("SENSOR", f"alarma en {fmt(tile)}; ARGOS investiga", "alarma")
        self.argos.notify_sensor(self, tile)
        self.argos.think_timer = min(self.argos.think_timer, 0.04)

    def raise_alarm(self, tile: Coord, source: str) -> None:
        self.security = min(config.SECURITY_MAX, self.security + config.SENSOR_SECURITY)
        self.stats["alarms"] += 1
        self.add_ring(tile, config.COL_RED, 1.0, 3.5)
        self.set_flash(config.COL_RED, 0.45)
        self.log_event(source, f"alerta: Ícaro detectado en {fmt(tile)}", "alarma")
        self.argos.notify_sensor(self, tile)
        self.argos.think_timer = min(self.argos.think_timer, 0.04)

    def drone_report(self, drone: Drone, position: Coord) -> None:
        drone.reports += 1
        self.stats["drone_reports"] += 1
        self.security = min(config.SECURITY_MAX, self.security + config.DRONE_SECURITY)
        self.add_ring(position, drone.color, 0.8, 2.4)
        self.log_event(
            drone.name,
            f"¡Ícaro avistado en {fmt(position)}! reportando a ARGOS",
            "mensaje",
        )
        self.argos.receive_report(self, drone.name, position)
        self.argos.think_timer = min(self.argos.think_timer, 0.04)

    # ------------------------------------------------------------------
    # Bloqueo de corredores (criterio de aceptación)
    # ------------------------------------------------------------------
    def preview_blockade(self, door: Coord) -> dict | None:
        """Comprueba una puerta sin modificar la partida ni el grafo."""
        if self.state != "playing" or door not in self.maze.doors:
            return None
        if self.maze.is_locked(door):
            return None
        occupied = {self.player.tile, self.argos.tile}
        occupied.update(drone.tile for drone in self.drones)
        if door in occupied:
            return None

        objectives = self.player_objectives()
        route = dijkstra(self.maze.graph, self.player.tile, objectives)
        if not route.found:
            return None
        targets = set(self.remaining_cards) | {self.maze.exit}
        if not self.maze.targets_reachable_without(
            door, start=self.player.tile, targets=targets
        ):
            return None

        self.maze.graph.set_blocked(door, True)
        try:
            alternative = dijkstra(self.maze.graph, self.player.tile, objectives)
        finally:
            self.maze.graph.set_blocked(door, False)
        if not alternative.found or alternative.cost <= route.cost + 1e-9:
            return None
        if alternative.cost > max(route.cost * 4.0, route.cost + 80.0):
            return None
        return {
            "door": door,
            "before": route.cost,
            "after": alternative.cost,
            "duration": config.DOOR_LOCK_TIME,
            "objective": route.goal,
        }

    def try_blockade(self, source: str, *, by_argos: bool = False,
                     door: Coord | None = None) -> dict | None:
        if self.state != "playing":
            return None
        if door is not None:
            candidates = [(door, 0)]
        else:
            objectives = self.player_objectives()
            route = dijkstra(self.maze.graph, self.player.tile, objectives)
            if not route.found:
                return None
            candidates: list[tuple[Coord, int]] = []
            for index, tile in enumerate(route.path):
                if index < 1:
                    continue
                if tile in self.maze.doors and tile not in self.maze.locked_doors:
                    candidates.append((tile, index))
            if not candidates:
                fallback = [
                    tile for tile in self.maze.doors
                    if tile not in self.maze.locked_doors
                ]
                fallback.sort(key=lambda tile: manhattan(tile, self.player.tile))
                candidates = [(tile, 0) for tile in fallback]

        for candidate, _index in candidates:
            preview = self.preview_blockade(candidate)
            if preview is None:
                continue
            self.maze.lock_door(candidate, self.time, config.DOOR_LOCK_TIME)
            self.stats["blocks"] += 1
            result = {**preview, "time": self.time, "source": source}
            self.acceptance_tests.append(result)
            self.add_ring(candidate, config.COL_RED, 0.9, 2.4)
            self.add_text(candidate, "BLOQUEO", config.COL_RED)
            self.set_flash(config.COL_RED if by_argos else config.COL_AMBER, 0.28)
            if by_argos:
                self.log_event(
                    "ARGOS",
                    f"bloquea puerta {fmt(candidate)}: coste de Ícaro "
                    f"{preview['before']:.0f} → {preview['after']:.0f} · alternativa válida",
                    "bloqueo",
                )
            else:
                self.log_event(
                    source,
                    f"cierra corredor en {fmt(candidate)} durante {config.DOOR_LOCK_TIME:.0f}s "
                    f"(coste {preview['before']:.0f} → {preview['after']:.0f})",
                    "bloqueo",
                )
            return result
        if not by_argos:
            self.log_event(
                "PRUEBA",
                "no se encontró una puerta bloqueable con ruta alternativa",
                "info",
            )
        return None

    # ------------------------------------------------------------------
    # Bucle de simulación
    # ------------------------------------------------------------------
    def update(self, dt: float, move_dir: Coord | None = None) -> None:
        if self.state != "playing":
            return
        dt = max(0.0, min(dt, 0.10))
        self.time += dt
        if self.time >= config.TIME_LIMIT:
            self.time = config.TIME_LIMIT
            self._lose("El tiempo de emergencia se ha agotado")
            return
        self._update_effects(dt)

        for tile in self.maze.unlock_expired(self.time):
            self.log_event("SISTEMA", f"puerta {fmt(tile)} desbloqueada", "bloqueo")
            self.add_ring(tile, config.COL_GREEN, 0.5, 1.4)

        self.security = max(0.0, self.security - config.SECURITY_DECAY_PER_S * dt)
        if self.argos.player_visible:
            self.security = min(
                config.SECURITY_MAX,
                self.security + config.ARGOS_SECURITY_PER_S * dt,
            )

        # Energía del traje.
        self.player.energy -= config.ENERGY_DRAIN_PER_S * dt
        self.player.step_timer = max(0.0, self.player.step_timer - dt)
        self.player.update_visual(dt)
        if self.player.energy <= 0.0:
            self.player.energy = 0.0
            self._lose("La energía del traje se ha agotado")
            return

        if self.autopilot:
            self.bot.update(self, dt)
        elif move_dir is not None and self.player.step_timer <= 0.0:
            self.attempt_player_move(move_dir)

        if self.state != "playing":
            return
        if self.argos.tile == self.player.tile:
            self._lose("ARGOS ha capturado a Ícaro")
            return

        self.argos.update(self, dt)
        for drone in self.drones:
            drone.update(self, dt)

        if self.argos.tile == self.player.tile:
            self._lose("ARGOS ha capturado a Ícaro")
            return
        if self.player.energy <= 0.0:
            self.player.energy = 0.0
            self._lose("La energía del traje se ha agotado")
            return

    def _win(self) -> None:
        if self.state != "playing":
            return
        self.state = "won"
        self.end_reason = "Ícaro alcanzó la compuerta de emergencia"
        self.end_time = self.time
        self.add_ring(self.maze.exit, config.COL_GREEN, 1.4, 4.0)
        self.log_event("ÍCARO", "¡escape logrado! compuerta de emergencia cruzada", "logro")
        self._finish_log()

    def _lose(self, reason: str) -> None:
        if self.state != "playing":
            return
        self.state = "lost"
        self.end_reason = reason
        self.end_time = self.time
        self.add_ring(self.player.tile, config.COL_RED, 1.2, 3.2)
        self.set_flash(config.COL_RED, 0.8)
        self.log_event("SISTEMA", f"partida perdida: {reason}", "error")
        self._finish_log()

    # ------------------------------------------------------------------
    # Métricas / cierre
    # ------------------------------------------------------------------
    def register_search(self, agent, d_result, a_result) -> None:
        self.stats["searches"] += 2
        for result in (d_result, a_result):
            bucket = self.search_stats[result.algorithm]
            bucket["count"] += 1
            bucket["nodes"] += result.expanded
            bucket["ms"] += result.elapsed_ms
            bucket["peak"] = max(bucket["peak"], result.frontier_peak)
            if result.found:
                bucket["found"] += 1
        self.recent_searches.append({
            "time": self.time,
            "agent": getattr(agent, "name", "—"),
            "d_nodes": d_result.expanded,
            "a_nodes": a_result.expanded,
            "d_ms": d_result.elapsed_ms,
            "a_ms": a_result.elapsed_ms,
        })

    def stats_summary(self) -> dict[str, str]:
        d = self.search_stats[config.ALGO_DIJKSTRA]
        a = self.search_stats[config.ALGO_ASTAR]
        def mean(bucket, field):
            return bucket[field] / bucket["count"] if bucket["count"] else 0.0
        saved = 0.0
        if d["nodes"] > 0:
            saved = 100.0 * (1.0 - a["nodes"] / d["nodes"])
        return {
            "tiempo": f"{self.end_time if self.state != 'playing' else self.time:.1f}s",
            "tarjetas": f"{len(self.player.cards)}/{config.CARD_COUNT}",
            "energía": f"{self.player.energy:.0f}",
            "seguridad": f"{self.security:.0f}",
            "alarmas": str(self.stats["alarms"]),
            "bloqueos": str(self.stats["blocks"]),
            "hackeos": str(self.stats["hacks"]),
            "búsquedas": str(self.stats["searches"]),
            "dijkstra_nodos": f"{mean(d, 'nodes'):.1f}",
            "astar_nodos": f"{mean(a, 'nodes'):.1f}",
            "ahorro_nodos": f"{saved:.1f}%",
            "dijkstra_ms": f"{mean(d, 'ms'):.3f}",
            "astar_ms": f"{mean(a, 'ms'):.3f}",
        }

    def _finish_log(self) -> None:
        if self._closed or not self.log_file:
            return
        summary = self.stats_summary()
        lines = [
            f"FIN: {self.state.upper()} · {self.end_reason}",
            "MÉTRICAS DE LA PARTIDA",
        ]
        lines.extend(f"  {key}: {value}" for key, value in summary.items())
        if self.acceptance_tests:
            lines.append("PRUEBAS DE BLOQUEO DE CORREDOR")
            for item in self.acceptance_tests:
                lines.append(
                    f"  t={item['time']:.1f}s {item['source']} puerta {item['door']} "
                    f"coste {item['before']:.0f}→{item['after']:.0f}"
                )
        self.log_file.summary(lines)
        self.log_file.close()
        self._closed = True

    def close(self) -> None:
        if not self._closed:
            if self.state == "playing":
                self.log_event("SISTEMA", "sesión cerrada por el usuario", "sistema")
            self._finish_log()
