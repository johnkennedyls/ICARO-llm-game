"""Aplicación Pygame: ventana escalable, entrada, estados y bucle principal."""

from __future__ import annotations

import asyncio
import os
import queue
import random
import threading
from datetime import datetime
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEO_CENTERED", "1")

import pygame

from . import config
from .game import Game
from .render import Renderer


class App:
    def __init__(self, seed: int = config.DEFAULT_SEED,
                 cells_x: int = config.DEFAULT_CELLS_X,
                 cells_y: int = config.DEFAULT_CELLS_Y,
                 *, start: bool = False, autopilot: bool = False) -> None:
        self.seed = seed
        self.cells_x = cells_x
        self.cells_y = cells_y
        self.start_immediately = start
        self.autopilot_default = autopilot
        self.mode = "title"  # title | playing | paused | ended
        self.game: Game | None = None
        self.running = True
        self._screenshot_requested = False
        self._fullscreen = False
        self._windowed_size = (config.WINDOW_W, config.WINDOW_H)
        self._llm_tasks: queue.Queue = queue.Queue()
        self._llm_results: queue.Queue = queue.Queue()
        self._llm_pending = {"operator": False, "analyst": False}
        self._llm_worker: threading.Thread | None = None
        self._init_pygame()

    # ------------------------------------------------------------------
    # Inicialización
    # ------------------------------------------------------------------
    def _init_pygame(self) -> None:
        pygame.init()
        pygame.display.set_caption(f"{config.APP_NAME} · {config.APP_SUBTITLE}")
        pygame.key.set_repeat(0)
        desktop = pygame.display.get_desktop_sizes()
        desktop_w, desktop_h = desktop[0] if desktop else (config.WINDOW_W, config.WINDOW_H)
        w = max(900, min(config.WINDOW_W, desktop_w - 80))
        h = int(w * config.WINDOW_H / config.WINDOW_W)
        if h > desktop_h - 100:
            h = max(540, desktop_h - 100)
            w = int(h * config.WINDOW_W / config.WINDOW_H)
        self._windowed_size = (w, h)
        self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
        self.canvas = pygame.Surface((config.WINDOW_W, config.WINDOW_H)).convert()
        self.renderer = Renderer(self.canvas)
        self.clock = pygame.time.Clock()
        pygame.display.set_icon(self._make_icon())
        if self.start_immediately:
            self._start_game(self.seed)

    def _make_icon(self) -> pygame.Surface:
        icon = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.circle(icon, (8, 16, 24), (32, 32), 31)
        pygame.draw.circle(icon, config.COL_CYAN, (32, 32), 28, 2)
        pygame.draw.circle(icon, config.COL_RED, (32, 32), 12)
        pygame.draw.circle(icon, (255, 220, 225), (36, 28), 3)
        return icon

    # ------------------------------------------------------------------
    # Juego
    # ------------------------------------------------------------------
    def _start_game(self, seed: int) -> None:
        previous = self.game
        algorithm = previous.algorithm if previous else config.ALGO_ASTAR
        fog = previous.fog_enabled if previous else True
        paths = previous.show_paths if previous else True
        autopilot = previous.autopilot if previous else self.autopilot_default
        if previous:
            previous.close()
        self.game = Game(seed=seed, cells_x=self.cells_x, cells_y=self.cells_y)
        self.game.algorithm = algorithm
        self.game.fog_enabled = fog
        self.game.show_paths = paths
        if autopilot:
            self.game.toggle_autopilot()
        self.renderer.reset_fog()
        self.mode = "playing"
        self.seed = seed

    def _new_seed(self) -> int:
        rng = random.SystemRandom()
        while True:
            candidate = rng.randint(1, 9999)
            if candidate != self.seed:
                return candidate

    def _restart(self, new_seed: bool = False) -> None:
        if self.game is None:
            if self.mode == "title":
                if new_seed:
                    self.seed = self._new_seed()
            return
        seed = self._new_seed() if new_seed else self.game.seed
        self._start_game(seed)

    def _close_game(self) -> None:
        if self.game is not None:
            self.game.close()
            self.game = None

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------
    def run(self) -> None:
        try:
            while self.running:
                dt = min(0.10, self.clock.tick(config.FPS) / 1000.0)
                self.renderer.tick(dt)
                self._handle_events()
                if not self.running:
                    break
                self._update(dt)
                self._draw()
                if self._screenshot_requested:
                    self._save_screenshot()
                    self._screenshot_requested = False
                self._present()
        finally:
            self._close_game()
            self._stop_llm_worker()
            pygame.quit()

    def _update(self, dt: float) -> None:
        if self.mode == "playing" and self.game is not None:
            move = self._movement()
            self.game.update(dt, move)
            self._drain_llm_results()
            if self.mode == "playing" and self.game is not None:
                self._schedule_analyst(self.game)
            if self.game.state != "playing":
                self.mode = "ended"

    def _draw(self) -> None:
        if self.mode == "title":
            self.renderer.draw_title(self.seed, self.cells_x, self.cells_y,
                                     self.clock.get_fps())
        elif self.game is not None:
            self.renderer.draw_game(self.game, self.clock.get_fps())
            if self.mode == "paused":
                self.renderer.draw_pause(self.game)
            elif self.mode == "ended":
                self.renderer.draw_end(self.game)

    def _present(self) -> None:
        sw, sh = self.screen.get_size()
        scale = min(sw / config.WINDOW_W, sh / config.WINDOW_H)
        dst_w = max(1, int(config.WINDOW_W * scale))
        dst_h = max(1, int(config.WINDOW_H * scale))
        self.screen.fill((0, 0, 0))
        if (dst_w, dst_h) == (config.WINDOW_W, config.WINDOW_H):
            scaled = self.canvas
        else:
            scaled = pygame.transform.smoothscale(self.canvas, (dst_w, dst_h))
        self.screen.blit(scaled, ((sw - dst_w) // 2, (sh - dst_h) // 2))
        pygame.display.flip()

    def _movement(self) -> tuple[int, int] | None:
        keys = pygame.key.get_pressed()
        left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        right = keys[pygame.K_d] or keys[pygame.K_RIGHT]
        up = keys[pygame.K_w] or keys[pygame.K_UP]
        down = keys[pygame.K_s] or keys[pygame.K_DOWN]
        dx = int(right) - int(left)
        dy = int(down) - int(up)
        if dx:
            return dx, 0
        if dy:
            return 0, dy
        return None

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------
    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE and not self._fullscreen:
                width = max(800, event.w)
                height = max(500, event.h)
                self._windowed_size = (width, height)
                self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event)

    def _handle_key(self, event: pygame.event.Event) -> None:
        key = event.key
        if key == pygame.K_F11:
            self._toggle_fullscreen()
            return
        if key == pygame.K_F12:
            self._screenshot_requested = True
            return

        if self.mode == "title":
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self._start_game(self.seed)
            elif key == pygame.K_n:
                self.seed = self._new_seed()
            elif key == pygame.K_ESCAPE:
                self.running = False
            return

        if self.mode == "paused":
            if key == pygame.K_ESCAPE:
                self.mode = "playing"
            elif key == pygame.K_r:
                self._restart(new_seed=False)
            elif key == pygame.K_n:
                self._restart(new_seed=True)
            elif key == pygame.K_q:
                self._close_game()
                self.mode = "title"
            return

        if self.mode == "ended":
            if key == pygame.K_r:
                self._restart(new_seed=False)
            elif key == pygame.K_n:
                self._restart(new_seed=True)
            elif key == pygame.K_ESCAPE:
                self._close_game()
                self.mode = "title"
            return

        if self.game is None:
            return

        if key == pygame.K_ESCAPE:
            self.mode = "paused"
        elif key == pygame.K_p:
            self.game.toggle_autopilot()
        elif key == pygame.K_e:
            self.game.hack_terminal()
        elif key == pygame.K_TAB:
            backwards = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
            self.game.cycle_panel(-1 if backwards else 1)
        elif pygame.K_1 <= key <= pygame.K_4:
            self.game.select_panel(key - pygame.K_1)
        elif key == pygame.K_F1:
            self.game.toggle_algorithm()
        elif key == pygame.K_F2:
            self.game.show_paths = not self.game.show_paths
            state = "visibles" if self.game.show_paths else "ocultas"
            self.game.log_event("SISTEMA", f"rutas planificadas {state}", "sistema")
        elif key == pygame.K_F3:
            self.game.fog_enabled = not self.game.fog_enabled
            state = "activada" if self.game.fog_enabled else "desactivada"
            self.game.log_event("SISTEMA", f"niebla de guerra {state}", "sistema")
        elif key == pygame.K_F5:
            self.game.force_blockade()
        elif key == pygame.K_F6:
            self.game.trigger_demo_alarm()
        elif key == pygame.K_h:
            self._talk_to_operator()
        elif key == pygame.K_r:
            self._restart(new_seed=False)
        elif key == pygame.K_n:
            self._restart(new_seed=True)

    def _ensure_llm_worker(self) -> None:
        if self._llm_worker is None:
            self._llm_worker = threading.Thread(
                target=self._llm_loop, name="icaro-llm", daemon=True
            )
            self._llm_worker.start()

    def _llm_loop(self) -> None:
        while True:
            task = self._llm_tasks.get()
            if task is None:
                return
            game, kind, agent, context = task
            try:
                response = asyncio.run(agent.think_async(context))
                error = None
            except Exception as exc:
                response = None
                error = str(exc)
            self._llm_results.put((game, kind, response, error))

    def _stop_llm_worker(self) -> None:
        if self._llm_worker is not None:
            self._llm_tasks.put(None)
            self._llm_worker = None

    def _request_llm(self, game: Game, kind: str, agent, context: str) -> None:
        if agent is None or self._llm_pending[kind]:
            return
        self._llm_pending[kind] = True
        self._ensure_llm_worker()
        self._llm_tasks.put((game, kind, agent, context))

    def _schedule_analyst(self, game: Game) -> None:
        if game.analyst is not None and game.analyst.should_analyze(game):
            self._request_llm(
                game, "analyst", game.analyst, game.analyst.build_context(game)
            )

    def _drain_llm_results(self) -> None:
        from .llm_agents import LLMActionValidator

        while True:
            try:
                game, kind, response, error = self._llm_results.get_nowait()
            except queue.Empty:
                return
            self._llm_pending[kind] = False
            if game is not self.game or game.state != "playing":
                continue
            if error or response is None or response.error:
                reason = error or (response.error if response else "respuesta vacía")
                game.log_event("OPERADOR" if kind == "operator" else "ANALISTA",
                               f"error LLM: {reason}", "error")
                continue

            validator = LLMActionValidator(game)
            if kind == "operator":
                events = game.operator.process_response(game, response, validator)
                for event in events:
                    event_type = event["type"]
                    if event_type == "dialogue":
                        text = event["text"]
                        game.log_event("OPERADOR", text, "llm")
                        game.add_text(game.player.tile, text[:40], config.COL_CYAN, 2.0)
                    elif event_type == "tool_validated":
                        game.log_event(
                            "OPERADOR",
                            f"sugerencia validada: {event['tool']} {event.get('args', {})}",
                            "llm",
                        )
                    elif event_type == "action_executed":
                        game.log_event(
                            "OPERADOR", f"acción ejecutada: {event['action']}", "llm"
                        )
                continue

            events = game.analyst.process_response(game, response, validator)
            for event in events:
                if event["type"] != "analyst_suggestion":
                    continue
                tool = event["tool"]
                args = event["args"]
                if tool == "suggest_blockade":
                    result = game.try_blockade(
                        "ANALISTA_LLM", by_argos=True, door=args["door"]
                    )
                    if result is None:
                        game.log_event("ANALISTA", "el bloqueo dejó de ser válido", "sistema")
                    else:
                        game.log_event(
                            "ANALISTA",
                            f"bloqueo ejecutado: {args['rationale']}",
                            "llm",
                        )
                else:
                    game.log_event(
                        "ANALISTA", f"sugerencia: {tool} {args}", "llm"
                    )

    def _talk_to_operator(self) -> None:
        game = self.game
        if game is None or game.operator is None:
            if game is not None:
                game.log_event("SISTEMA", "Operador no disponible (LLM deshabilitado)", "info")
            return
        if game.state != "playing":
            return
        self._request_llm(
            game, "operator", game.operator,
            game.operator.build_context(game, trigger="manual"),
        )

    def _toggle_fullscreen(self) -> None:
        if not self._fullscreen:
            self._windowed_size = self.screen.get_size()
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            self._fullscreen = True
        else:
            self.screen = pygame.display.set_mode(self._windowed_size, pygame.RESIZABLE)
            self._fullscreen = False

    # ------------------------------------------------------------------
    # Capturas
    # ------------------------------------------------------------------
    def _save_screenshot(self) -> None:
        folder = Path(__file__).resolve().parent.parent / "capturas"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = folder / f"icaro_{stamp}.png"
            pygame.image.save(self.canvas, str(path))
            if self.game is not None:
                self.game.log_event("SISTEMA", f"captura guardada en {path.name}", "sistema")
                self.game.set_flash(config.COL_GREEN, 0.25)
        except OSError:
            pass


def run(seed: int = config.DEFAULT_SEED,
        cells_x: int = config.DEFAULT_CELLS_X,
        cells_y: int = config.DEFAULT_CELLS_Y,
        *, start: bool = False, autopilot: bool = False) -> None:
    App(seed=seed, cells_x=cells_x, cells_y=cells_y,
        start=start, autopilot=autopilot).run()
