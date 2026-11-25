"""Dibujo del mundo: baldosas, niebla, rutas, agentes, efectos y alertas."""

from __future__ import annotations

import math

import pygame

from .. import config
from ..graph import Coord
from .base import RendererBase


class WorldMixin(RendererBase):
    # ------------------------------------------------------------------
    # Composición general
    # ------------------------------------------------------------------
    def draw_game(self, game, fps: float = 0.0) -> None:
        self.fps = fps
        self.background()
        self.layout_map(game)
        self.update_visibility(game)
        self._draw_maze(game)
        self._draw_flash(game)
        self.vignette()
        self.draw_hud(game)
        self.draw_panel(game)
        self.draw_footer(game, fps)

    # ------------------------------------------------------------------
    # Laberinto
    # ------------------------------------------------------------------
    def _draw_maze(self, game) -> None:
        frame = pygame.Rect(config.MAZE_RECT)
        self.panel(frame, config.COL_PANEL_DARK, config.COL_PANEL_EDGE, radius=16)
        map_rect = self._map_rect
        pygame.draw.rect(self.canvas, (3, 6, 10), map_rect.inflate(6, 6),
                         border_radius=4)
        self.text("SECTOR 07 · RED DE SENSORES", map_rect.x, frame.y + 8, 9,
                  config.COL_DIM, bold=True)
        self.text(f"{game.maze.width}×{game.maze.height} · {game.maze.graph.vertices} vértices",
                  map_rect.right, frame.y + 8, 9, config.COL_DIM, anchor="topright")

        previous_clip = self.canvas.get_clip()
        self.canvas.set_clip(map_rect)
        self._draw_tiles(game)
        self._draw_features(game)
        self._draw_fog(game)
        self._draw_player_glow(game)
        self._draw_paths(game)
        self._draw_agents(game)
        self._draw_effects(game)
        self._draw_badges(game)
        self._draw_terminal_prompt(game)
        self.scanline(map_rect, config.COL_CYAN, 8)
        self.canvas.set_clip(previous_clip)

        pygame.draw.rect(self.canvas, (36, 58, 78), map_rect.inflate(2, 2),
                         width=1, border_radius=2)

    def _draw_tiles(self, game) -> None:
        maze = game.maze
        tile_px = self._tile_px
        open_tiles = maze.open_tiles
        for y in range(maze.height):
            for x in range(maze.width):
                tile = (x, y)
                rect = self.tile_rect(tile)
                if tile not in open_tiles:
                    seed = (x * 73856093) ^ (y * 19349663)
                    shade = 2 + ((seed >> 3) & 3)
                    wall = (
                        config.COL_WALL[0] + shade,
                        config.COL_WALL[1] + shade,
                        config.COL_WALL[2] + shade,
                    )
                    pygame.draw.rect(self.canvas, wall, rect)
                    pygame.draw.line(
                        self.canvas, config.COL_WALL_TOP,
                        (rect.x, rect.y), (rect.right - 1, rect.y), 2,
                    )
                    pygame.draw.line(
                        self.canvas, (34, 49, 66),
                        (rect.x, rect.y), (rect.x, rect.bottom - 1),
                    )
                    pygame.draw.line(
                        self.canvas, config.COL_WALL_SHADOW,
                        (rect.x + 1, rect.bottom - 2), (rect.right - 2, rect.bottom - 2),
                    )
                else:
                    base = config.COL_FLOOR_2 if (x + y) % 2 else config.COL_FLOOR
                    pygame.draw.rect(self.canvas, base, rect)
                    pygame.draw.line(
                        self.canvas, config.COL_GRID,
                        (rect.right - 1, rect.y), (rect.right - 1, rect.bottom - 1),
                    )
                    pygame.draw.line(
                        self.canvas, config.COL_GRID,
                        (rect.x, rect.bottom - 1), (rect.right - 1, rect.bottom - 1),
                    )
                    seed = (x * 92837111) ^ (y * 689287499)
                    if tile_px >= 18 and seed % 23 == 0:
                        pygame.draw.line(
                            self.canvas, (21, 38, 52),
                            (rect.x + 4, rect.bottom - 5),
                            (rect.x + 8, rect.bottom - 5),
                        )
                    if tile_px >= 22 and seed % 47 == 0:
                        pygame.draw.circle(
                            self.canvas, (28, 48, 63),
                            (rect.right - 5, rect.y + 5), 1,
                        )

        # Inicio del jugador.
        if game.maze.start and self.known(game, game.maze.start):
            rect = self.tile_rect(game.maze.start)
            pygame.draw.circle(self.canvas, (33, 73, 72), rect.center,
                               int(tile_px * 0.34), 1)
            self.text("INICIO", rect.centerx, rect.centery - int(tile_px * 0.55),
                      7, (67, 120, 118), anchor="center")

    def _draw_features(self, game) -> None:
        maze = game.maze
        for tile in maze.hazards:
            if self.known(game, tile):
                self._draw_hazard(tile)
        for tile in maze.sensors:
            if self.known(game, tile):
                self._draw_sensor(tile, game.sensors_active)
        for tile in maze.terminals:
            if self.known(game, tile):
                self._draw_terminal(tile, tile in game.used_terminals)
        for tile in maze.doors:
            if self.known(game, tile):
                self._draw_door(tile, game)
        for tile in maze.cards:
            if tile not in game.player.cards and self.known(game, tile):
                self._draw_card(tile)
        if self.known(game, maze.exit):
            self._draw_exit(game)

    def _draw_hazard(self, tile: Coord) -> None:
        rect = self.tile_rect(tile)
        size = self._tile_px
        color = (142, 61, 36)
        for offset in (0.38, 0.62):
            y = rect.y + int(size * offset)
            pygame.draw.line(
                self.canvas, color,
                (rect.x + 4, y + 3), (rect.x + size - 4, y - 2), 2,
            )
        pygame.draw.circle(
            self.canvas, (224, 112, 55),
            (rect.centerx, rect.centery), max(1, size // 13),
        )
        alpha = 45 + int(25 * (0.5 + 0.5 * math.sin(self.ui_time * 2.4 + tile[0])))
        self.glow((rect.centerx, rect.centery), int(size * 0.7), (190, 82, 40), alpha)

    def _draw_sensor(self, tile: Coord, active: bool) -> None:
        rect = self.tile_rect(tile)
        size = self._tile_px
        center = rect.center
        color = config.COL_PURPLE if active else (82, 91, 110)
        pulse = 0.5 + 0.5 * math.sin(self.ui_time * 2.2 + tile[0] * 0.7 + tile[1])
        radius = max(3, int(size * (0.22 + 0.05 * pulse)))
        self.glow(center, int(size * 0.85), color, 26 if active else 10)
        pygame.draw.circle(self.canvas, color, center, radius, 1)
        pygame.draw.circle(self.canvas, color, center, max(1, size // 11))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            pygame.draw.line(
                self.canvas, color,
                (center[0] + dx * radius, center[1] + dy * radius),
                (center[0] + dx * (radius + 3), center[1] + dy * (radius + 3)),
                1,
            )

    def _draw_terminal(self, tile: Coord, used: bool) -> None:
        rect = self.tile_rect(tile)
        size = self._tile_px
        color = (85, 104, 120) if used else config.COL_CYAN
        box = pygame.Rect(0, 0, int(size * 0.48), int(size * 0.36))
        box.center = (rect.centerx, rect.centery)
        pygame.draw.rect(self.canvas, (8, 20, 27), box, border_radius=2)
        pygame.draw.rect(self.canvas, color, box, width=1, border_radius=2)
        for i in range(2):
            pygame.draw.line(
                self.canvas, (color[0] // 2, color[1] // 2, color[2] // 2),
                (box.x + 3, box.y + 5 + i * 4), (box.right - 3, box.y + 5 + i * 4),
            )
        pygame.draw.line(self.canvas, color, (box.centerx, box.bottom),
                         (box.centerx, box.bottom + 3))
        if not used:
            self.glow((rect.centerx, rect.centery), int(size * 0.8),
                      config.COL_CYAN, 25)

    def _draw_card(self, tile: Coord) -> None:
        rect = self.tile_rect(tile)
        size = self._tile_px
        bob = math.sin(self.ui_time * 3.0 + tile[0] * 0.9 + tile[1] * 0.4) * 2
        center = (rect.centerx, int(rect.centery + bob))
        w = max(7, int(size * 0.40))
        h = max(10, int(size * 0.54))
        self.glow(center, int(size * 0.9), config.COL_CYAN, 40)
        points = [
            (center[0], center[1] - h // 2),
            (center[0] + w // 2, center[1]),
            (center[0], center[1] + h // 2),
            (center[0] - w // 2, center[1]),
        ]
        pygame.draw.polygon(self.canvas, (10, 42, 51), points)
        pygame.draw.polygon(self.canvas, config.COL_CYAN, points, 1)
        pygame.draw.line(self.canvas, (205, 252, 255),
                         (center[0], center[1] - h // 3),
                         (center[0], center[1] + h // 3), 1)
        pygame.draw.line(self.canvas, config.COL_CYAN,
                         (center[0] - w // 3, center[1] - 2),
                         (center[0] + w // 3, center[1] - 2), 1)

    def _draw_door(self, tile: Coord, game) -> None:
        rect = self.tile_rect(tile)
        size = self._tile_px
        orientation = game.maze.door_orientation(tile)
        locked = game.maze.is_locked(tile)
        if locked:
            color = config.COL_RED
            glow_alpha = 50 + int(18 * math.sin(self.ui_time * 6))
        else:
            color = config.COL_AMBER
            glow_alpha = 14
        self.glow(rect.center, int(size * 0.8), color, glow_alpha)
        if orientation == "horizontal":
            # Pasillo E-O: la puerta es una barrera vertical.
            pygame.draw.rect(self.canvas, (34, 29, 19),
                             pygame.Rect(rect.centerx - 2, rect.y + 2, 4, size - 4))
            for offset in (-4, 0, 4):
                pygame.draw.line(
                    self.canvas, color,
                    (rect.centerx + offset, rect.y + 4),
                    (rect.centerx + offset, rect.bottom - 4),
                    1 if locked else 1,
                )
            pygame.draw.rect(
                self.canvas, color,
                pygame.Rect(rect.centerx - 5, rect.y + 2, 10, 2),
            )
            pygame.draw.rect(
                self.canvas, color,
                pygame.Rect(rect.centerx - 5, rect.bottom - 4, 10, 2),
            )
        else:
            pygame.draw.rect(self.canvas, (34, 29, 19),
                             pygame.Rect(rect.x + 2, rect.centery - 2, size - 4, 4))
            for offset in (-4, 0, 4):
                pygame.draw.line(
                    self.canvas, color,
                    (rect.x + 4, rect.centery + offset),
                    (rect.right - 4, rect.centery + offset),
                    1,
                )
            pygame.draw.rect(
                self.canvas, color,
                pygame.Rect(rect.x + 2, rect.centery - 5, 2, 10),
            )
            pygame.draw.rect(
                self.canvas, color,
                pygame.Rect(rect.right - 4, rect.centery - 5, 2, 10),
            )
        if locked:
            pygame.draw.rect(
                self.canvas, (255, 92, 110),
                pygame.Rect(rect.centerx - 3, rect.centery - 2, 6, 6), 1,
            )
            pygame.draw.arc(
                self.canvas, (255, 140, 150),
                pygame.Rect(rect.centerx - 3, rect.centery - 5, 6, 7),
                0, math.pi, 1,
            )

    def _draw_exit(self, game) -> None:
        rect = self.tile_rect(game.maze.exit)
        size = self._tile_px
        active = game.exit_active
        color = config.COL_GREEN if active else (132, 72, 79)
        pulse = 0.5 + 0.5 * math.sin(self.ui_time * 3.4)
        self.glow(rect.center, int(size * (1.2 if active else 0.8)),
                  color, 65 if active else 18)
        pygame.draw.rect(
            self.canvas, (10, 25, 22) if active else (22, 16, 20),
            rect.inflate(-int(size * 0.35), -int(size * 0.25)), border_radius=2,
        )
        pygame.draw.rect(
            self.canvas, color,
            rect.inflate(-int(size * 0.35), -int(size * 0.25)), 1, border_radius=2,
        )
        for offset in (-4, 0, 4):
            pygame.draw.line(
                self.canvas, color,
                (rect.centerx + offset, rect.y + int(size * 0.24)),
                (rect.centerx + offset, rect.bottom - int(size * 0.24)), 1,
            )
        if active:
            r = int(size * (0.38 + 0.05 * pulse))
            pygame.draw.circle(self.canvas, color, rect.center, r, 1)
            self.text("SALIDA", rect.centerx, rect.y - 3, 7, color,
                      bold=True, anchor="midbottom")

    # ------------------------------------------------------------------
    # Niebla / iluminación
    # ------------------------------------------------------------------
    def _draw_fog(self, game) -> None:
        if not game.fog_enabled:
            return
        map_rect = self._map_rect
        overlay = pygame.Surface(map_rect.size, pygame.SRCALPHA)
        explored = self._explored
        visible = self._visible
        for y in range(game.maze.height):
            for x in range(game.maze.width):
                tile = (x, y)
                if tile in visible:
                    continue
                alpha = 48 if tile in explored else 196
                overlay.fill((0, 0, 0, alpha), self.local_rect(tile))
        self.canvas.blit(overlay, map_rect.topleft)

    def _draw_player_glow(self, game) -> None:
        center = self.center_visual(game.player.visual)
        radius = int(self._tile_px * 3.0)
        self.glow(center, radius, config.COL_CYAN, 25)
        self.glow(center, int(self._tile_px * 1.2), config.COL_GREEN, 25)

    # ------------------------------------------------------------------
    # Rutas planificadas
    # ------------------------------------------------------------------
    def _draw_paths(self, game) -> None:
        if not game.show_paths:
            return
        map_rect = self._map_rect
        layer = pygame.Surface(map_rect.size, pygame.SRCALPHA)

        def local_center(tile: Coord) -> tuple[int, int]:
            return (
                tile[0] * self._tile_px + self._tile_px // 2,
                tile[1] * self._tile_px + self._tile_px // 2,
            )

        def draw_path(agent, color, width=2, dot_alpha=155, selected=True) -> None:
            origin = getattr(agent, "tile", game.player.tile)
            path = [origin, *agent.path]
            if len(path) < 1:
                return
            if len(path) > 1:
                points = [local_center(tile) for tile in path]
                faded = (*color, 48 if not selected else 82)
                pygame.draw.lines(layer, faded, False, points, width)
            for index, tile in enumerate(path):
                if not selected and index % 2:
                    continue
                center = local_center(tile)
                alpha = dot_alpha if selected else 54
                radius = max(1, self._tile_px // 10)
                if index % 4 == 0:
                    radius += 1
                    alpha = min(255, alpha + 25)
                pygame.draw.circle(layer, (*color, alpha), center, radius)
            if agent.goal is not None:
                gx, gy = local_center(agent.goal)
                pulse = int(4 + 2 * math.sin(self.ui_time * 5))
                pygame.draw.circle(layer, (*color, 210), (gx, gy),
                                   max(5, self._tile_px // 3), 1)
                pygame.draw.line(layer, (*color, 150), (gx - pulse, gy),
                                 (gx + pulse, gy), 1)
                pygame.draw.line(layer, (*color, 150), (gx, gy - pulse),
                                 (gx, gy + pulse), 1)

        argos_color = (
            config.COL_RED if game.argos.state in ("CAZA", "INTERCEPTA")
            else config.COL_AMBER if game.argos.state == "INVESTIGA"
            else (166, 118, 61)
        )
        draw_path(game.argos, argos_color, width=2, selected=True)

        if game.argos.prediction is not None and game.argos.prediction.target is not None:
            px, py = local_center(game.argos.prediction.target)
            pulse = 3 + int(2 * (0.5 + 0.5 * math.sin(self.ui_time * 4)))
            pygame.draw.circle(layer, (*config.COL_PURPLE, 150), (px, py),
                               max(4, self._tile_px // 2), 1)
            pygame.draw.circle(layer, (*config.COL_PURPLE, 210), (px, py), pulse, 1)

        if game.autopilot:
            draw_path(game.bot, config.COL_CYAN, width=2, dot_alpha=160, selected=True)

        for index, drone in enumerate(game.drones):
            selected = game.panel_index == index + 1
            draw_path(
                drone,
                drone.color,
                width=1,
                dot_alpha=105 if selected else 35,
                selected=selected,
            )

        self.canvas.blit(layer, map_rect.topleft)

    # ------------------------------------------------------------------
    # Agentes
    # ------------------------------------------------------------------
    def _draw_agents(self, game) -> None:
        argos_visible = self.is_agent_visible(game, game.argos)
        if argos_visible:
            self._draw_argos(game)
        for drone in game.drones:
            if self.is_agent_visible(game, drone):
                self._draw_drone(game, drone)
        self._draw_player(game)

    def _draw_player(self, game) -> None:
        player = game.player
        cx, cy = self.center_visual(player.visual)
        tile = self._tile_px
        body = max(5, int(tile * 0.30))
        color = config.COL_GREEN
        self.glow((cx, cy), int(tile * 1.35), color, 54)
        pygame.draw.circle(self.canvas, (7, 24, 22), (int(cx), int(cy)), body + 2)
        pygame.draw.circle(self.canvas, color, (int(cx), int(cy)), body, 2)
        fx, fy = player.facing
        tip = (cx + fx * (body + 5), cy + fy * (body + 5))
        left = (cx - fy * body * 0.7, cy + fx * body * 0.7)
        right = (cx + fy * body * 0.7, cy - fx * body * 0.7)
        pygame.draw.polygon(self.canvas, color, [tip, left, right], 1)
        pygame.draw.circle(self.canvas, (224, 255, 242),
                           (int(cx), int(cy)), max(1, body // 3))
        if game.autopilot:
            radius = body + 7
            for i in range(4):
                start = self.ui_time * 1.8 + i * math.pi / 2
                pygame.draw.arc(
                    self.canvas, config.COL_CYAN,
                    pygame.Rect(int(cx - radius), int(cy - radius),
                                radius * 2, radius * 2),
                    start, start + 0.7, 1,
                )
            self.text("IA", cx, cy - radius - 4, 8, config.COL_CYAN,
                      bold=True, anchor="midbottom")
        self.text("ÍCARO", cx, cy + body + 7, 8, color, bold=True,
                  anchor="midtop", shadow=True)

    def _draw_argos(self, game) -> None:
        argos = game.argos
        cx, cy = self.center_visual(argos.visual)
        tile = self._tile_px
        body = max(6, int(tile * 0.36))
        revealed_only = game.reveal_active and argos.tile not in self._visible
        color = (255, 118, 132) if revealed_only else config.COL_RED
        self.glow((cx, cy), int(tile * 2.1), color, 55)
        pygame.draw.circle(self.canvas, (28, 8, 14), (int(cx), int(cy)), body + 4)
        pygame.draw.circle(self.canvas, color, (int(cx), int(cy)), body + 4, 1)
        segments = 4
        for i in range(segments):
            start = self.ui_time * 1.4 + i * math.tau / segments
            pygame.draw.arc(
                self.canvas, color,
                pygame.Rect(int(cx - body - 3), int(cy - body - 3),
                            (body + 3) * 2, (body + 3) * 2),
                start, start + 0.55, 2,
            )
        pygame.draw.circle(self.canvas, (66, 14, 24), (int(cx), int(cy)), body)
        pygame.draw.circle(self.canvas, color, (int(cx), int(cy)), body, 1)
        iris = max(2, body // 3)
        pygame.draw.circle(self.canvas, (255, 210, 214), (int(cx), int(cy)), iris)
        pygame.draw.circle(self.canvas, (25, 5, 8), (int(cx), int(cy)), max(1, iris // 2))
        scan_angle = self.ui_time * 2.0
        ex = cx + math.cos(scan_angle) * body
        ey = cy + math.sin(scan_angle) * body
        pygame.draw.line(self.canvas, (255, 186, 193), (cx, cy), (ex, ey), 1)
        if argos.state in ("CAZA", "INTERCEPTA"):
            pygame.draw.circle(self.canvas, color, (int(cx), int(cy)),
                               body + 9 + int(2 * math.sin(self.ui_time * 6)), 1)
        label = "ARGOS" if not revealed_only else "ARGOS · REVELADO"
        self.text(label, cx, cy + body + 8, 8, color, bold=True,
                  anchor="midtop", shadow=True)
        if argos.player_visible and game.fog_enabled:
            pc = self.center_visual(game.player.visual)
            layer = pygame.Surface(self._map_rect.size, pygame.SRCALPHA)
            offset = self._map_rect.topleft
            pygame.draw.line(
                layer, (*config.COL_RED, 28 + int(18 * (0.5 + 0.5 * math.sin(self.ui_time * 4)))),
                (cx - offset[0], cy - offset[1]), (pc[0] - offset[0], pc[1] - offset[1]), 1,
            )
            self.canvas.blit(layer, offset)

    def _draw_drone(self, game, drone) -> None:
        cx, cy = self.center_visual(drone.visual)
        tile = self._tile_px
        size = max(4, int(tile * 0.23))
        color = drone.color
        revealed_only = game.reveal_active and drone.tile not in self._visible
        self.glow((cx, cy), int(tile * 1.2), color, 40)
        points = [
            (cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy),
        ]
        pygame.draw.polygon(self.canvas, (8, 22, 30), points)
        pygame.draw.polygon(self.canvas, color, points, 1)
        pygame.draw.circle(self.canvas, color, (int(cx), int(cy)), max(1, size // 3), 1)
        blink = (math.sin(self.ui_time * 5 + hash(drone.name) % 10) + 1) / 2
        pygame.draw.circle(
            self.canvas, (255, 255, 255),
            (int(cx + size * 0.7), int(cy - size * 0.7)), 1 if blink < 0.5 else 2,
        )
        label = drone.name.upper() if not revealed_only else f"{drone.name.upper()} · REV"
        self.text(label, cx, cy + size + 5, 7, color, bold=True,
                  anchor="midtop", shadow=True)

    # ------------------------------------------------------------------
    # Efectos, avisos, insignias
    # ------------------------------------------------------------------
    def _draw_effects(self, game) -> None:
        map_rect = self._map_rect
        layer = pygame.Surface(map_rect.size, pygame.SRCALPHA)
        for effect in game.effects:
            age = effect["age"]
            duration = effect["duration"]
            progress = min(1.0, age / max(0.001, duration))
            cx = effect["tile"][0] * self._tile_px + self._tile_px // 2
            cy = effect["tile"][1] * self._tile_px + self._tile_px // 2
            if effect["kind"] == "ring":
                radius = int(self._tile_px * (0.4 + effect["max_radius"] * progress))
                alpha = int(210 * (1.0 - progress))
                pygame.draw.circle(layer, (*effect["color"], alpha), (cx, cy),
                                   max(2, radius), 2)
                if radius > 6:
                    pygame.draw.circle(layer, (*effect["color"], alpha // 3),
                                       (cx, cy), max(1, radius - 4), 1)
            elif effect["kind"] == "text":
                alpha = int(255 * (1.0 - progress ** 1.8))
                surface = self.text_surface(effect["text"], 9, effect["color"], True)
                surface = surface.copy()
                surface.set_alpha(alpha)
                rect = surface.get_rect(midbottom=(cx, int(cy - self._tile_px * 0.35 - 12 * progress)))
                shadow_surface = self.text_surface(effect["text"], 9, (0, 0, 0), True).copy()
                shadow_surface.set_alpha(alpha)
                layer.blit(shadow_surface, (rect.x + 1, rect.y + 2))
                layer.blit(surface, rect)
        self.canvas.blit(layer, map_rect.topleft)

    def _draw_badges(self, game) -> None:
        x = self._map_rect.x + 8
        y = self._map_rect.y + 8
        if game.autopilot:
            rect = self.draw_pill(x, y, "PILOTO IA", config.COL_CYAN)
            y += rect.h + 5
        if game.sensors_remaining > 0:
            rect = self.draw_pill(
                x, y, f"SENSORES OFF {game.sensors_remaining:.0f}s", config.COL_PURPLE
            )
            y += rect.h + 5
        if game.reveal_active:
            rect = self.draw_pill(
                x, y, f"ARGOS REVELADO {game.reveal_until - game.time:.0f}s", config.COL_RED
            )
            y += rect.h + 5
        if game.security >= 75:
            self.draw_pill(x, y, "ALERTA CRÍTICA", config.COL_RED)

    def _draw_terminal_prompt(self, game) -> None:
        terminal = game.nearest_terminal()
        if terminal is None:
            return
        text = "E · HACKEAR TERMINAL · −5 ENERGÍA"
        width = self.text_width(text, 10, bold=True) + 16
        self.draw_pill(
            self._map_rect.centerx - width // 2,
            self._map_rect.bottom - 31,
            text,
            config.COL_CYAN, size=10,
        )

    def _draw_flash(self, game) -> None:
        if game.flash <= 0.01 and game.security < 55:
            return
        map_rect = self._map_rect
        if game.flash > 0.01:
            layer = pygame.Surface(map_rect.size, pygame.SRCALPHA)
            layer.fill((*game.flash_color, int(70 * game.flash)))
            self.canvas.blit(layer, map_rect.topleft)
        if game.security >= 55:
            pulse = 0.5 + 0.5 * math.sin(self.ui_time * 4.5)
            alpha = int((game.security - 55) / 45 * 80 * pulse)
            layer = pygame.Surface(map_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(
                layer, (*config.COL_RED, alpha),
                pygame.Rect(0, 0, map_rect.w, map_rect.h), width=3,
            )
            self.canvas.blit(layer, map_rect.topleft)
