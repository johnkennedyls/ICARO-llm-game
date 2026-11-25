"""Aplicación Pygame: ventana escalable, entrada, estados y bucle principal."""

from __future__ import annotations

import os
import random
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
            pygame.quit()

    def _update(self, dt: float) -> None:
        if self.mode == "playing" and self.game is not None:
            move = self._movement()
            self.game.update(dt, move)
            
            # Analista síncrono (cada ~2 segundos si hay triggers)
            if self.game.analyst is not None and self.game.analyst.should_analyze(self.game):
                try:
                    context = self.game.analyst.build_context(self.game)
                    response = self.game.analyst.think_sync(context)
                    from .llm_agents import LLMActionValidator
                    validator = LLMActionValidator(self.game)
                    events = self.game.analyst.process_response(self.game, response, validator)
                    for event in events:
                        if event["type"] != "analyst_suggestion":
                            continue
                        tool = event["tool"]
                        args = event["args"]
                        if tool == "suggest_blockade":
                            result = self.game.try_blockade(
                                "ANALISTA_LLM", by_argos=True, door=args["door"]
                            )
                            if result is None:
                                self.game.log_event("ANALISTA", "el bloqueo dejó de ser válido", "sistema")
                            else:
                                self.game.log_event(
                                    "ANALISTA",
                                    f"bloqueo ejecutado: {args['rationale']}",
                                    "llm",
                                )
                        else:
                            self.game.log_event(
                                "ANALISTA", f"sugerencia: {tool} {args}", "llm"
                            )
                except Exception as exc:
                    self.game.log_event("ANALISTA", f"Error LLM: {exc}", "error")
            
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
