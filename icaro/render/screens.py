"""Pantallas de título, pausa y resultados."""

from __future__ import annotations

import math

import pygame

from .. import config
from .base import RendererBase
from .ui import LOG_COLORS


class ScreensMixin(RendererBase):
    # ------------------------------------------------------------------
    # Título
    # ------------------------------------------------------------------
    def draw_title(self, seed: int, cells_x: int, cells_y: int,
                   fps: float = 0.0) -> None:
        self.fps = fps
        self.background()
        self.glow((1070, 340), 330, (120, 22, 38), 40)
        self.glow((570, 240), 380, (18, 60, 78), 30)
        self.dust(config.COL_CYAN_DIM, 35)
        layer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        pygame.draw.line(layer, (36, 65, 82, 80), (0, 64), (self.width, 64))
        self.canvas.blit(layer, (0, 0))
        self.scanline(pygame.Rect(0, 0, self.width, self.height),
                      config.COL_CYAN, 10)

        self.text("FUNDACIÓN UNIVERSITARIA DE POPAYÁN · ALGORITMOS COMPUTACIONALES",
                  84, 48, 10, config.COL_MUTED, bold=True)
        self.text("PROYECTO FINAL · IA AGÉNTICA · LABERINTO DE SUPERVIVENCIA",
                  84, 68, 9, config.COL_RED, bold=True)
        self.text("EL ESCAPE", 82, 102, 62, config.COL_TEXT, bold=True)
        self.text("DE ÍCARO", 82, 176, 62, config.COL_CYAN, bold=True)
        pygame.draw.line(self.canvas, config.COL_CYAN, (84, 264), (640, 264), 2)
        self.glow((240, 264), 100, config.COL_CYAN, 30)

        story = (
            "Ícaro despierta en una estación subterránea cuyo sistema de seguridad "
            "ha perdido el control. La compuerta de emergencia exige tres tarjetas, "
            "pero ARGOS registra cada movimiento y modifica tus rutas para interceptarte."
        )
        for index, line in enumerate(self.wrapped_lines(story, 15, 610, 3)):
            self.text(line, 84, 292 + index * 24, 15, config.COL_MUTED)

        chips = [
            ("DIJKSTRA", config.COL_AMBER),
            ("A*", config.COL_CYAN),
            ("HEURÍSTICA ADMISIBLE", config.COL_PURPLE),
            ("PREDICCIÓN RECURSIVA", config.COL_GREEN),
            ("MULTIAGENTE", config.COL_BLUE),
        ]
        x = 84
        y = 392
        for label, color in chips:
            width = self.text_width(label, 9, bold=True) + 16
            if x + width > 700:
                x = 84
                y += 32
            self.draw_pill(x, y, label, color, size=9)
            x += width + 8

        self.text("01  RECOGE 3 TARJETAS", 84, 466, 11, config.COL_TEXT, bold=True)
        self.text("02  EVITA A ARGOS", 300, 466, 11, config.COL_TEXT, bold=True)
        self.text("03  CRUZA LA COMPUERTA", 500, 466, 11, config.COL_TEXT, bold=True)
        pygame.draw.line(self.canvas, (34, 53, 69), (84, 484), (676, 484))

        self.panel(pygame.Rect(74, 502, 630, 124), (8, 14, 22, 205),
                   (29, 48, 65), radius=10)
        controls_left = [
            ("WASD / ↑↓←→", "mover a Ícaro"),
            ("E / H", "terminal / operador LLM"),
            ("P", "piloto automático"),
            ("TAB / 1-4", "agente en el panel"),
        ]
        controls_right = [
            ("F1", "A* ↔ Dijkstra"),
            ("F2", "rutas planificadas"),
            ("F5 / F6", "bloqueo / alarma demo"),
            ("ESC", "pausa / controles"),
        ]
        for column, controls in enumerate((controls_left, controls_right)):
            cx = 96 + column * 310
            for row, (key, action) in enumerate(controls):
                cy = 518 + row * 24
                key_w = max(58, self.text_width(key, 9, bold=True, mono=True) + 14)
                pygame.draw.rect(self.canvas, (14, 25, 37),
                                 pygame.Rect(cx, cy, key_w, 17), border_radius=4)
                pygame.draw.rect(self.canvas, (43, 67, 86),
                                 pygame.Rect(cx, cy, key_w, 17), width=1,
                                 border_radius=4)
                self.text(key, cx + key_w // 2, cy + 8, 8, config.COL_CYAN,
                          bold=True, mono=True, anchor="center")
                self.text(action, cx + key_w + 8, cy + 5, 9, config.COL_MUTED)

        pulse = 0.5 + 0.5 * math.sin(self.ui_time * 3.2)
        prompt_rect = pygame.Rect(84, 646, 330, 46)
        prompt_color = (
            int(config.COL_CYAN[0] * (0.7 + 0.3 * pulse)),
            int(config.COL_CYAN[1] * (0.7 + 0.3 * pulse)),
            int(config.COL_CYAN[2] * (0.7 + 0.3 * pulse)),
        )
        pygame.draw.rect(self.canvas, (12, 42, 51), prompt_rect, border_radius=7)
        pygame.draw.rect(self.canvas, prompt_color, prompt_rect, width=1,
                         border_radius=7)
        self.glow((prompt_rect.centerx, prompt_rect.centery), 80,
                  config.COL_CYAN, int(18 + 20 * pulse))
        self.text("ENTER · INICIAR PARTIDA", prompt_rect.centerx,
                  prompt_rect.centery, 17, prompt_color, bold=True, anchor="center")
        self.text(
            f"SEMILLA {seed} · MAPA {2 * cells_x + 1}×{2 * cells_y + 1} · "
            "[N] nueva semilla · [F11] pantalla completa",
            84, 704, 9, config.COL_DIM,
        )
        self.text("Pulsa ESC para salir", 84, 722, 9, config.COL_DIM)

        self._draw_title_eye((1080, 356), 186)
        self.hline(84, self.width - 84, 762, (22, 35, 48))
        self.text("Proyecto final · Algoritmos Computacionales · 2026-2",
                  84, 770, 9, config.COL_DIM)
        self.text(f"{fps:.0f} FPS", self.width - 84, 770, 9, config.COL_DIM,
                  anchor="topright")

    def _draw_title_eye(self, center: tuple[int, int], radius: int) -> None:
        cx, cy = center
        layer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        # Anillos de radar.
        for r, alpha, width in ((radius + 62, 38, 1), (radius + 16, 48, 1),
                                (radius - 22, 34, 1)):
            pygame.draw.circle(layer, (*config.COL_CYAN_DIM, alpha), (cx, cy), r, width)
        for i in range(36):
            angle = i * math.tau / 36
            inner = radius + 8 if i % 3 else radius + 3
            outer = radius + 18
            bx1 = cx + math.cos(angle) * inner
            by1 = cy + math.sin(angle) * inner
            bx2 = cx + math.cos(angle) * outer
            by2 = cy + math.sin(angle) * outer
            pygame.draw.line(layer, (58, 101, 119, 68), (bx1, by1), (bx2, by2), 1)
        sweep = self.ui_time * 0.55
        points = [(cx, cy)]
        for step in range(7):
            angle = sweep + step * 0.045
            points.append((cx + math.cos(angle) * (radius + 60),
                           cy + math.sin(angle) * (radius + 60)))
        pygame.draw.polygon(layer, (26, 135, 151, 20), points)

        self.canvas.blit(layer, (0, 0))
        self.glow(center, radius + 40, (130, 23, 42), 55)
        pygame.draw.circle(self.canvas, (13, 8, 13), center, radius - 26)
        pygame.draw.circle(self.canvas, (80, 20, 31), center, radius - 26, 2)
        pygame.draw.circle(self.canvas, (34, 10, 16), center, radius - 58, 1)
        for i in range(4):
            start = -self.ui_time * 0.6 + i * math.tau / 4
            pygame.draw.arc(
                self.canvas, config.COL_RED,
                pygame.Rect(cx - radius + 8, cy - radius + 8,
                            (radius - 8) * 2, (radius - 8) * 2),
                start, start + 0.55, 3,
            )
        # Ojo.
        eye_rect = pygame.Rect(cx - 122, cy - 56, 244, 112)
        pygame.draw.ellipse(self.canvas, (25, 7, 13), eye_rect)
        pygame.draw.ellipse(self.canvas, (119, 26, 42), eye_rect, 2)
        self.glow(center, 95, (190, 35, 56), 85)
        pygame.draw.circle(self.canvas, (63, 7, 18), center, 54)
        pygame.draw.circle(self.canvas, (238, 60, 78), center, 54, 2)
        pygame.draw.circle(self.canvas, (255, 100, 116), center, 32)
        pygame.draw.circle(self.canvas, (25, 2, 7), center, 20)
        pygame.draw.circle(self.canvas, (255, 230, 232), (cx + 13, cy - 12), 5)
        angle = self.ui_time * 1.7
        pygame.draw.line(
            self.canvas, (255, 161, 170),
            center, (cx + math.cos(angle) * 74, cy + math.sin(angle) * 74), 1,
        )
        for i in range(4):
            start = self.ui_time * 0.8 + i * math.tau / 4
            pygame.draw.arc(
                self.canvas, (255, 106, 124),
                pygame.Rect(cx - 72, cy - 72, 144, 144),
                start, start + 0.36, 2,
            )

        # Etiquetas del radar.
        labels = [("A*", -0.8), ("DIJKSTRA", 2.3), ("h(n)", 3.8)]
        for text, angle in labels:
            lx = cx + math.cos(angle) * (radius + 42)
            ly = cy + math.sin(angle) * (radius + 42)
            self.text(text, int(lx), int(ly), 9, config.COL_CYAN_DIM,
                      bold=True, anchor="center")
        for i, (text, angle) in enumerate(
            (("T1", -2.35), ("T2", 0.25), ("T3", 1.9))
        ):
            lx = cx + math.cos(angle) * (radius + 58)
            ly = cy + math.sin(angle) * (radius + 58)
            pygame.draw.circle(self.canvas, config.COL_CYAN, (int(lx), int(ly)), 3)
            pygame.draw.circle(self.canvas, (24, 70, 80), (int(lx), int(ly)), 7, 1)
            self.text(text, int(lx), int(ly) - 2, 7, config.COL_CYAN,
                      anchor="center")

        self.text("ARGOS", cx, cy + radius + 76, 23, config.COL_RED,
                  bold=True, anchor="center", shadow=True)
        self.text("GUARDIÁN AUTÓNOMO · CAZADOR A*", cx, cy + radius + 106, 9,
                  config.COL_DIM, bold=True, anchor="center")
        self.text("PERCEPCIÓN → MEMORIA → PLANIFICACIÓN", cx,
                  cy + radius + 123, 8, config.COL_CYAN_DIM, anchor="center")

    # ------------------------------------------------------------------
    # Pausa
    # ------------------------------------------------------------------
    def draw_pause(self, game) -> None:
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((2, 4, 8, 205))
        self.canvas.blit(overlay, (0, 0))
        panel = pygame.Rect(270, 116, 860, 568)
        self.panel(panel, (9, 15, 24), (35, 58, 77), radius=16)
        pygame.draw.line(self.canvas, config.COL_CYAN,
                         (panel.x + 28, panel.y + 8), (panel.x + 210, panel.y + 8), 2)
        self.text("PAUSA", panel.x + 32, panel.y + 30, 32, config.COL_TEXT, bold=True)
        self.text("SIMULACIÓN DETENIDA · EL LABERINTO SIGUE ESPERANDO",
                  panel.x + 34, panel.y + 74, 10, config.COL_MUTED, bold=True)

        stats = game.stats_summary()
        left = panel.x + 34
        top = panel.y + 116
        self.text("CONTROLES", left, top, 10, config.COL_DIM, bold=True)
        for index, (key, action) in enumerate(config.CONTROLS):
            column = index // 7
            row = index % 7
            x = left + column * 405
            y = top + 26 + row * 24
            pygame.draw.rect(self.canvas, (14, 25, 37),
                             pygame.Rect(x, y, 92, 18), border_radius=4)
            pygame.draw.rect(self.canvas, (42, 65, 84),
                             pygame.Rect(x, y, 92, 18), width=1, border_radius=4)
            self.text(key, x + 46, y + 9, 8, config.COL_CYAN, bold=True,
                      anchor="center")
            self.text(action, x + 102, y + 4, 10, config.COL_MUTED)

        # Estado en una fila propia, debajo de los controles.
        state_y = top + 212
        self.text("ESTADO DE LA PARTIDA", left, state_y, 10, config.COL_DIM, bold=True)
        rows = [
            ("Tiempo", stats["tiempo"]),
            ("Tarjetas", stats["tarjetas"]),
            ("Energía", stats["energía"]),
            ("Seguridad", stats["seguridad"]),
            ("Algoritmo", "A*" if game.algorithm == config.ALGO_ASTAR else "Dijkstra"),
            ("Búsquedas", stats["búsquedas"]),
            ("Ahorro A*", stats["ahorro_nodos"]),
            ("Autopiloto", "ON" if game.autopilot else "OFF"),
        ]
        for index, (label, value) in enumerate(rows):
            row = index // 4
            col = index % 4
            x = left + col * 200
            y = state_y + 24 + row * 42
            self.text(label, x, y, 9, config.COL_MUTED)
            color = config.COL_CYAN if label == "Ahorro A*" else config.COL_TEXT
            self.text(value, x, y + 13, 14, color, bold=True, mono=True)
        self.text("ESC continuar · R reiniciar misma semilla · Q título",
                  panel.centerx, panel.bottom - 34, 11, config.COL_CYAN,
                  bold=True, anchor="center")
        self.text("El panel de monitoreo registra cada plan, mensaje y bloqueo.",
                  panel.centerx, panel.bottom - 14, 9, config.COL_DIM,
                  anchor="center")

    # ------------------------------------------------------------------
    # Fin de partida
    # ------------------------------------------------------------------
    def draw_end(self, game) -> None:
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((2, 4, 8, 218))
        self.canvas.blit(overlay, (0, 0))
        panel = pygame.Rect(292, 92, 816, 616)
        if game.state == "won":
            accent = config.COL_GREEN
            title = "FUGA LOGRADA"
        elif game.state == "lost" and "energía" in game.end_reason.lower():
            accent = config.COL_AMBER
            title = "SIN ENERGÍA"
        elif game.state == "lost" and "tiempo" in game.end_reason.lower():
            accent = config.COL_AMBER
            title = "TIEMPO AGOTADO"
        else:
            accent = config.COL_RED
            title = "ÍCARO CAPTURADO"
        self.glow((panel.centerx, panel.y + 20), 260, accent, 45)
        self.panel(panel, (8, 14, 22), accent, radius=16, width=2)
        pygame.draw.line(self.canvas, accent, (panel.x + 30, panel.y + 8),
                         (panel.x + 250, panel.y + 8), 2)
        self.text(title, panel.centerx, panel.y + 30, 38, accent, bold=True,
                  anchor="midtop", shadow=True)
        self.text(game.end_reason, panel.centerx, panel.y + 78, 12,
                  config.COL_MUTED, anchor="midtop")

        stats = game.stats_summary()
        grid = [
            ("TIEMPO", stats["tiempo"], config.COL_TEXT),
            ("TARJETAS", stats["tarjetas"], config.COL_CYAN),
            ("ENERGÍA", stats["energía"], config.COL_GREEN),
            ("SEGURIDAD", stats["seguridad"], config.COL_AMBER),
            ("ALARMAS", stats["alarmas"], config.COL_PURPLE),
            ("BLOQUEOS", stats["bloqueos"], config.COL_RED),
            ("HACKEOS", stats["hackeos"], config.COL_CYAN),
            ("BÚSQUEDAS", stats["búsquedas"], config.COL_TEXT),
            ("BLOQUEOS VERIF.", f"{len(game.acceptance_tests)}", config.COL_GREEN),
        ]
        start_x = panel.x + 44
        start_y = panel.y + 112
        cell_w = 238
        cell_h = 64
        for index, (label, value, color) in enumerate(grid):
            row = index // 3
            col = index % 3
            x = start_x + col * cell_w
            y = start_y + row * cell_h
            pygame.draw.rect(self.canvas, (12, 21, 31),
                             pygame.Rect(x, y, cell_w - 14, cell_h - 12),
                             border_radius=7)
            self.text(label, x + 12, y + 9, 8, config.COL_DIM, bold=True)
            self.text(value, x + 12, y + 23, 22, color, bold=True, mono=True)

        chart_y = start_y + 3 * cell_h + 14
        self.text("DIJKSTRA vs A* · DATOS REALES DE LA PARTIDA",
                  start_x, chart_y, 9, config.COL_DIM, bold=True)
        d = game.search_stats[config.ALGO_DIJKSTRA]
        a = game.search_stats[config.ALGO_ASTAR]
        avg_d = d["nodes"] / d["count"] if d["count"] else 0
        avg_a = a["nodes"] / a["count"] if a["count"] else 0
        max_nodes = max(1, avg_d, avg_a)
        bar_x = start_x + 90
        bar_w = 470
        for index, (label, search_stats, avg, color) in enumerate((
            ("Dijkstra", d, avg_d, config.COL_AMBER),
            ("A*", a, avg_a, config.COL_CYAN),
        )):
            y = chart_y + 24 + index * 30
            self.text(label, start_x, y, 11, color, bold=True)
            pygame.draw.rect(self.canvas, (13, 23, 34),
                             pygame.Rect(bar_x, y, bar_w, 14), border_radius=5)
            if avg > 0:
                pygame.draw.rect(
                    self.canvas, color,
                    pygame.Rect(bar_x, y, int(bar_w * avg / max_nodes), 14),
                    border_radius=5,
                )
            self.text(f"{avg:.1f} nodos", bar_x + bar_w + 12, y - 1, 10,
                      config.COL_TEXT)
            ms = (search_stats["ms"] / search_stats["count"]
                  if search_stats["count"] else 0)
            self.text(f"{ms:.2f} ms", bar_x + bar_w + 92, y - 1, 9,
                      config.COL_MUTED)
        saved = stats["ahorro_nodos"]
        comparison_color = config.COL_GREEN if not saved.startswith("-") else config.COL_AMBER
        comparison = "reduce" if not saved.startswith("-") else "aumenta"
        self.text(f"A* {comparison} los nodos expandidos un {saved.lstrip('-')} respecto a Dijkstra",
                  start_x, chart_y + 92, 10, comparison_color)

        self.text(
            "El registro completo de planes, mensajes y métricas se guardó en la carpeta logs/.",
            panel.centerx, panel.bottom - 62, 9, config.COL_DIM, anchor="center",
        )
        prompt_y = panel.bottom - 38
        self._end_key(panel.x + 40, prompt_y, "R", "reiniciar misma semilla")
        self._end_key(panel.x + 300, prompt_y, "N", "nueva semilla")
        self._end_key(panel.x + 540, prompt_y, "ESC", "volver al título")
        self.text(f"Semilla {game.seed} · {game.maze.size_label} · "
                  f"{'piloto IA' if game.autopilot else 'control manual'}",
                  panel.right - 28, panel.bottom - 20, 8, config.COL_DIM,
                  anchor="topright")

    def _end_key(self, x: int, y: int, key: str, label: str) -> None:
        key_w = max(26, self.text_width(key, 9, bold=True) + 12)
        pygame.draw.rect(self.canvas, (15, 26, 38),
                         pygame.Rect(x, y, key_w, 18), border_radius=4)
        pygame.draw.rect(self.canvas, (45, 68, 87),
                         pygame.Rect(x, y, key_w, 18), width=1, border_radius=4)
        self.text(key, x + key_w // 2, y + 9, 9, config.COL_CYAN, bold=True,
                  anchor="center")
        self.text(label, x + key_w + 8, y + 4, 9, config.COL_MUTED)
