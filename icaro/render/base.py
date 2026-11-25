"""Utilidades de dibujo compartidas por el mundo, el panel y las pantallas."""

from __future__ import annotations

import math
import random

import pygame

from .. import config
from ..graph import Coord


class RendererBase:
    def __init__(self, canvas: pygame.Surface) -> None:
        self.canvas = canvas
        self.width, self.height = canvas.get_size()
        self.ui_time = 0.0
        self.fps = 0.0
        self._fonts: dict[tuple[int, bool, bool], pygame.font.Font] = {}
        self._text_cache: dict[tuple, pygame.Surface] = {}
        self._glow_cache: dict[tuple, pygame.Surface] = {}
        self._visible: set[Coord] = set()
        self._explored: set[Coord] = set()
        self._last_vis_at = -999.0
        self._last_player_tile: Coord | None = None
        self._map_rect = pygame.Rect(config.MAZE_RECT)
        self._tile_px = 26
        self._bg = self._make_background()
        self._vignette = self._make_vignette()
        rng = random.Random(2026)
        self._dust = [
            (rng.uniform(0, self.width), rng.uniform(0, self.height),
             rng.uniform(0.4, 1.8), rng.uniform(0, math.tau))
            for _ in range(80)
        ]

    # ------------------------------------------------------------------
    # Tiempo / niebla
    # ------------------------------------------------------------------
    def tick(self, dt: float) -> None:
        self.ui_time += dt

    def reset_fog(self) -> None:
        self._visible.clear()
        self._explored.clear()
        self._last_vis_at = -999.0
        self._last_player_tile = None

    def update_visibility(self, game) -> None:
        if not game.fog_enabled:
            return
        if (
            self._last_player_tile != game.player.tile
            or self.ui_time - self._last_vis_at >= 0.09
        ):
            visible = game.maze.graph.visible_tiles(
                game.player.tile, config.PLAYER_VISION
            )
            self._visible = visible
            self._explored |= visible
            self._last_player_tile = game.player.tile
            self._last_vis_at = self.ui_time

    def known(self, game, tile: Coord) -> bool:
        return not game.fog_enabled or tile in self._explored

    def is_agent_visible(self, game, agent) -> bool:
        if not game.fog_enabled:
            return True
        if game.reveal_active:
            return True
        return agent.tile in self._visible

    # ------------------------------------------------------------------
    # Fuentes y texto
    # ------------------------------------------------------------------
    def font(self, size: int, bold: bool = False, mono: bool = False) -> pygame.font.Font:
        key = (size, bold, mono)
        cached = self._fonts.get(key)
        if cached is None:
            names = (
                "consolas,dejavusansmono,couriernew"
                if mono else
                "segoeui,verdana,dejavusans,arial"
            )
            cached = pygame.font.SysFont(names, size, bold=bold)
            self._fonts[key] = cached
        return cached

    def text_surface(self, text: str, size: int, color: tuple[int, int, int],
                     bold: bool = False, mono: bool = False) -> pygame.Surface:
        key = (text, size, color, bold, mono)
        surface = self._text_cache.get(key)
        if surface is None:
            surface = self.font(size, bold, mono).render(text, True, color)
            if len(self._text_cache) > 3200:
                self._text_cache.clear()
            self._text_cache[key] = surface
        return surface

    def text(self, text: str, x: int, y: int, size: int,
             color: tuple[int, int, int] = config.COL_TEXT, *,
             bold: bool = False, mono: bool = False, anchor: str = "topleft",
             shadow: bool = False, max_width: int | None = None) -> pygame.Rect:
        if max_width is not None:
            text = self.fit_text(text, size, max_width, bold=bold, mono=mono)
        surface = self.text_surface(text, size, color, bold, mono)
        rect = surface.get_rect(**{anchor: (x, y)})
        if shadow:
            shadow_surface = self.text_surface(text, size, (0, 0, 0), bold, mono)
            self.canvas.blit(shadow_surface, (rect.x + 1, rect.y + 2))
        self.canvas.blit(surface, rect)
        return rect

    def text_width(self, text: str, size: int, bold: bool = False,
                   mono: bool = False) -> int:
        return self.font(size, bold, mono).size(text)[0]

    def fit_text(self, text: str, size: int, max_width: int,
                 bold: bool = False, mono: bool = False) -> str:
        if self.text_width(text, size, bold, mono) <= max_width:
            return text
        ellipsis = "…"
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.text_width(text[:mid] + ellipsis, size, bold, mono) <= max_width:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo].rstrip() + ellipsis

    def wrapped_lines(self, text: str, size: int, max_width: int, max_lines: int,
                      bold: bool = False, mono: bool = False) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if self.text_width(candidate, size, bold, mono) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
                if len(lines) == max_lines:
                    break
        if current and len(lines) < max_lines:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
        return lines

    def text_block(self, text: str, x: int, y: int, max_width: int, size: int,
                   color: tuple[int, int, int], max_lines: int = 2,
                   line_height: int | None = None) -> int:
        line_height = line_height or size + 3
        for index, line in enumerate(
            self.wrapped_lines(text, size, max_width, max_lines)
        ):
            self.text(line, x, y + index * line_height, size, color)
        return y + min(max_lines, max(1, len(text.split()) and max_lines)) * line_height

    # ------------------------------------------------------------------
    # Formas
    # ------------------------------------------------------------------
    def panel(self, rect, fill=config.COL_PANEL, border=config.COL_PANEL_EDGE,
              radius: int = 12, width: int = 1, alpha: int = 255,
              shadow: bool = True) -> pygame.Rect:
        rect = pygame.Rect(rect)
        if shadow:
            shadow_surface = pygame.Surface((rect.w + 20, rect.h + 20), pygame.SRCALPHA)
            pygame.draw.rect(
                shadow_surface, (0, 0, 0, 90),
                pygame.Rect(8, 10, rect.w, rect.h), border_radius=radius + 2,
            )
            self.canvas.blit(shadow_surface, (rect.x - 8, rect.y - 8))
        if alpha < 255:
            layer = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(
                layer, (*fill, alpha), pygame.Rect(0, 0, rect.w, rect.h),
                border_radius=radius,
            )
            if border:
                pygame.draw.rect(
                    layer, (*border, min(255, alpha + 40)),
                    pygame.Rect(0, 0, rect.w, rect.h), width=width,
                    border_radius=radius,
                )
            self.canvas.blit(layer, rect.topleft)
        else:
            pygame.draw.rect(self.canvas, fill, rect, border_radius=radius)
            if border:
                pygame.draw.rect(
                    self.canvas, border, rect, width=width, border_radius=radius
                )
        return rect

    def hline(self, x1: int, x2: int, y: int, color=config.COL_PANEL_EDGE,
              alpha: int = 255, width: int = 1) -> None:
        if alpha < 255:
            layer = pygame.Surface((max(1, x2 - x1), width + 2), pygame.SRCALPHA)
            pygame.draw.line(layer, (*color, alpha), (0, 1), (x2 - x1, 1), width)
            self.canvas.blit(layer, (x1, y))
        else:
            pygame.draw.line(self.canvas, color, (x1, y), (x2, y), width)

    # ------------------------------------------------------------------
    # Glow, fondos y decoración
    # ------------------------------------------------------------------
    def _glow(self, radius: int, color: tuple[int, int, int],
              alpha: int = 90) -> pygame.Surface:
        radius = max(2, int(radius))
        key = (radius, color, alpha)
        cached = self._glow_cache.get(key)
        if cached is None:
            surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            for r in range(radius, 0, -2):
                t = 1.0 - r / radius
                a = int(alpha * t * t)
                if a > 0:
                    pygame.draw.circle(
                        surface, (*color, a), (radius, radius), r
                    )
            cached = surface
            self._glow_cache[key] = cached
        return cached

    def glow(self, center: tuple[float, float], radius: int,
             color: tuple[int, int, int], alpha: int = 90) -> None:
        surface = self._glow(radius, color, alpha)
        self.canvas.blit(
            surface, (int(center[0] - radius), int(center[1] - radius)),
        )

    def _make_background(self) -> pygame.Surface:
        surf = pygame.Surface((self.width, self.height)).convert()
        top = config.COL_BG_2
        bottom = config.COL_BG
        for y in range(self.height):
            t = y / self.height
            color = (
                int(top[0] + (bottom[0] - top[0]) * t),
                int(top[1] + (bottom[1] - top[1]) * t),
                int(top[2] + (bottom[2] - top[2]) * t),
            )
            pygame.draw.line(surf, color, (0, y), (self.width, y))
        glow_layer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        for x in range(0, self.width, 46):
            pygame.draw.line(glow_layer, (24, 42, 58, 10), (x, 0), (x, self.height))
        for y in range(0, self.height, 46):
            pygame.draw.line(glow_layer, (24, 42, 58, 10), (0, y), (self.width, y))
        pygame.draw.circle(glow_layer, (38, 124, 152, 26), (250, 170), 300)
        pygame.draw.circle(glow_layer, (46, 36, 76, 30), (1120, 260), 380)
        surf.blit(glow_layer, (0, 0))
        return surf

    def _make_vignette(self) -> pygame.Surface:
        surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        steps = 90
        for i in range(steps):
            alpha = int(78 * (i / steps) ** 2)
            pygame.draw.rect(
                surf, (0, 0, 0, alpha),
                pygame.Rect(i, i, self.width - 2 * i, self.height - 2 * i),
                width=2,
            )
        return surf

    def background(self) -> None:
        self.canvas.blit(self._bg, (0, 0))

    def vignette(self) -> None:
        self.canvas.blit(self._vignette, (0, 0))

    def dust(self, color=config.COL_CYAN_DIM, alpha: int = 40) -> None:
        layer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        for base_x, base_y, speed, phase in self._dust:
            x = (base_x + speed * 4 * self.ui_time) % self.width
            y = (base_y + math.sin(self.ui_time * 0.3 + phase) * 14) % self.height
            pygame.draw.circle(layer, (*color, alpha), (int(x), int(y)), 1)
        self.canvas.blit(layer, (0, 0))

    def scanline(self, rect: pygame.Rect, color=config.COL_CYAN, alpha: int = 14) -> None:
        y = rect.y + int((self.ui_time * 38) % max(1, rect.h))
        layer = pygame.Surface((rect.w, 24), pygame.SRCALPHA)
        for i in range(24):
            a = int(alpha * (1 - abs(i - 12) / 12))
            pygame.draw.line(layer, (*color, a), (0, i), (rect.w, i))
        self.canvas.blit(layer, (rect.x, y - 12))

    # ------------------------------------------------------------------
    # Geometría del laberinto
    # ------------------------------------------------------------------
    def layout_map(self, game) -> pygame.Rect:
        width, height = game.maze.width, game.maze.height
        area = pygame.Rect(config.MAZE_RECT)
        usable_w = area.w - 20
        usable_h = area.h - 20
        tile = int(min(usable_w / width, usable_h / height))
        tile = max(7, min(tile, 34))
        self._tile_px = tile
        map_w = width * tile
        map_h = height * tile
        self._map_rect = pygame.Rect(
            area.x + (area.w - map_w) // 2,
            area.y + (area.h - map_h) // 2,
            map_w,
            map_h,
        )
        return self._map_rect

    @property
    def map_rect(self) -> pygame.Rect:
        return self._map_rect

    @property
    def tile_px(self) -> int:
        return self._tile_px

    def tile_rect(self, tile: Coord) -> pygame.Rect:
        x, y = tile
        return pygame.Rect(
            self._map_rect.x + x * self._tile_px,
            self._map_rect.y + y * self._tile_px,
            self._tile_px,
            self._tile_px,
        )

    def local_rect(self, tile: Coord, inset: int = 0) -> pygame.Rect:
        x, y = tile
        return pygame.Rect(
            x * self._tile_px + inset,
            y * self._tile_px + inset,
            self._tile_px - 2 * inset,
            self._tile_px - 2 * inset,
        )

    def center_of(self, tile: Coord) -> tuple[float, float]:
        rect = self.tile_rect(tile)
        return rect.centerx, rect.centery

    def center_visual(self, visual: list[float]) -> tuple[float, float]:
        return (
            self._map_rect.x + (visual[0] + 0.5) * self._tile_px,
            self._map_rect.y + (visual[1] + 0.5) * self._tile_px,
        )

    @staticmethod
    def clock_text(seconds: float) -> str:
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    @staticmethod
    def state_color(state: str) -> tuple[int, int, int]:
        state = state.upper()
        if any(key in state for key in ("CAZA", "INTERCEPTA", "CAPTUR", "PERDID")):
            return config.COL_RED
        if any(key in state for key in ("INVESTIGA", "ALERTA", "AVISTAMIENTO")):
            return config.COL_AMBER
        if any(key in state for key in ("PATRULLA", "EN RUTA", "PLANIFICA")):
            return config.COL_CYAN
        if any(key in state for key in ("SIN", "ERROR")):
            return config.COL_AMBER
        return config.COL_MUTED

    def draw_pill(self, x: int, y: int, text: str, color, *,
                  size: int = 10, bg_alpha: int = 35,
                  pad_x: int = 8, pad_y: int = 4) -> pygame.Rect:
        width = self.text_width(text, size, bold=True) + pad_x * 2
        height = size + pad_y * 2 + 1
        layer = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(
            layer, (*color, bg_alpha), pygame.Rect(0, 0, width, height),
            border_radius=height // 2,
        )
        pygame.draw.rect(
            layer, (*color, 110), pygame.Rect(0, 0, width, height),
            width=1, border_radius=height // 2,
        )
        self.canvas.blit(layer, (x, y))
        self.text(text, x + width // 2, y + height // 2, size, color,
                  bold=True, anchor="center")
        return pygame.Rect(x, y, width, height)
