"""HUD superior, panel de monitoreo en vivo y pie de página."""

from __future__ import annotations

import math

import pygame

from .. import config
from ..agents import PlayerBot, fmt
from .base import RendererBase

LOG_COLORS = {
    "plan": config.COL_CYAN,
    "replan": config.COL_BLUE,
    "percepcion": config.COL_MUTED,
    "mensaje": config.COL_PURPLE,
    "alarma": config.COL_RED,
    "bloqueo": config.COL_AMBER,
    "logro": config.COL_GREEN,
    "hack": config.COL_CYAN,
    "error": config.COL_RED,
    "aceptacion": config.COL_GREEN,
    "sistema": config.COL_MUTED,
    "memoria": config.COL_BLUE,
    "info": config.COL_TEXT,
}


class UIMixin(RendererBase):
    # ------------------------------------------------------------------
    # HUD
    # ------------------------------------------------------------------
    def draw_hud(self, game) -> None:
        self.panel(pygame.Rect(0, 0, self.width, 64), (8, 13, 21), None,
                   radius=0, shadow=False)
        pygame.draw.line(self.canvas, (33, 51, 69), (0, 63), (self.width, 63))
        pygame.draw.line(self.canvas, (15, 24, 35), (0, 64), (self.width, 64))
        self.glow((80, 32), 160, config.COL_CYAN, 18)

        title_left = "EL ESCAPE DE "
        width = self.text_width(title_left, 21, bold=True)
        self.text(title_left, 24, 10, 21, config.COL_TEXT, bold=True)
        self.text("ÍCARO", 24 + width, 10, 21, config.COL_CYAN, bold=True)
        self.text("LABERINTO DE SUPERVIVENCIA · GUARDIÁN ARGOS EN LÍNEA", 25, 38,
                  9, config.COL_MUTED, bold=True)

        # Tarjetas
        x = 370
        self._hud_label("TARJETAS", x, 10)
        for index in range(config.CARD_COUNT):
            slot = pygame.Rect(x + index * 27, 25, 20, 28)
            filled = index < len(game.player.cards)
            fill = (10, 46, 55) if filled else (12, 20, 30)
            border = config.COL_CYAN if filled else (40, 60, 78)
            pygame.draw.rect(self.canvas, fill, slot, border_radius=3)
            pygame.draw.rect(self.canvas, border, slot, width=1, border_radius=3)
            if filled:
                pygame.draw.line(self.canvas, (200, 253, 255),
                                 (slot.centerx, slot.y + 6),
                                 (slot.centerx, slot.bottom - 6), 1)
                pygame.draw.polygon(
                    self.canvas, config.COL_CYAN,
                    [(slot.centerx, slot.y + 4), (slot.right - 4, slot.centery),
                     (slot.centerx, slot.bottom - 4), (slot.x + 4, slot.centery)], 1,
                )
        self.text(f"{len(game.player.cards)}/{config.CARD_COUNT}", x + 87, 30,
                  15, config.COL_TEXT, bold=True, mono=True)

        # Compuerta
        gx = 498
        self._hud_label("COMPUERTA", gx, 10)
        active = game.exit_active
        color = config.COL_GREEN if active else config.COL_MUTED
        dot = 4
        pygame.draw.circle(self.canvas, color, (gx + dot, 33), dot)
        if active:
            self.glow((gx + dot, 33), 18, color, 60)
        self.text("ACTIVA" if active else "BLOQUEADA", gx + 13, 25, 12, color, bold=True)
        self.text("3 tarjetas" if not active else "corre a la salida", gx, 44, 9,
                  config.COL_DIM)

        # Energía
        ex = 630
        self._hud_label("ENERGÍA", ex, 10)
        ratio = max(0.0, min(1.0, game.player.energy / config.ENERGY_MAX))
        if ratio > 0.55:
            energy_color = config.COL_GREEN
        elif ratio > 0.25:
            energy_color = config.COL_AMBER
        else:
            energy_color = config.COL_RED
        self._bar(ex, 29, 150, 9, ratio, energy_color)
        self.text(f"{game.player.energy:3.0f}", ex + 162, 24, 15, energy_color,
                  bold=True, mono=True)
        self.text("consumo 0.85/s · vapor −4", ex, 44, 8, config.COL_DIM)

        # Tiempo
        tx = 852
        self._hud_label("TIEMPO RESTANTE", tx, 10)
        remaining = max(0.0, config.TIME_LIMIT - game.time)
        time_color = config.COL_RED if remaining <= 30 else config.COL_TEXT
        self.text(self.clock_text(remaining), tx, 24, 20, time_color,
                  bold=True, mono=True)
        self.text("semilla " + str(game.seed), tx, 44, 8, config.COL_DIM)

        # Alerta
        ax = 985
        self._hud_label("NIVEL DE ALERTA", ax, 10)
        sec_ratio = max(0.0, min(1.0, game.security / config.SECURITY_MAX))
        sec_color = (
            config.COL_RED if sec_ratio > 0.66
            else config.COL_AMBER if sec_ratio > 0.33
            else config.COL_CYAN
        )
        self._bar(ax, 29, 250, 8, sec_ratio, sec_color)
        self.text(f"{game.security:3.0f}%", ax + 262, 24, 14, sec_color,
                  bold=True, mono=True)
        if game.argos.player_visible:
            status = "ARGOS TE VE"
        elif game.argos.last_seen is not None and game.time - game.argos.last_seen_at < config.ARGOS_MEMORY_TTL:
            status = "ARGOS RASTREA"
        else:
            status = "SIN CONTACTO"
        pulse = 0.5 + 0.5 * math.sin(self.ui_time * 4)
        pygame.draw.circle(self.canvas, sec_color, (ax - 9, 12), 2 + int(pulse * 1.5))
        self.text(status, ax + 375, 8, 9, sec_color, bold=True, anchor="topright")
        self.text(f"ARGOS {config.ALGO_LABEL[game.algorithm]}",
                  ax, 44, 8, config.COL_DIM)
        self.text(f"alertas {game.stats['alarms']} · bloqueos {game.stats['blocks']}",
                  ax + 375, 44, 8, config.COL_DIM, anchor="topright")

        # Separador decorativo
        pygame.draw.line(self.canvas, (22, 36, 49), (946, 8), (946, 56))

    def _hud_label(self, text: str, x: int, y: int) -> None:
        self.text(text, x, y, 8, config.COL_DIM, bold=True)

    def _bar(self, x: int, y: int, w: int, h: int, ratio: float, color) -> None:
        pygame.draw.rect(self.canvas, (7, 12, 18), pygame.Rect(x, y, w, h),
                         border_radius=h // 2)
        if ratio > 0:
            pygame.draw.rect(
                self.canvas, color,
                pygame.Rect(x, y, max(2, int(w * ratio)), h),
                border_radius=h // 2,
            )
        pygame.draw.rect(self.canvas, (40, 58, 74), pygame.Rect(x, y, w, h),
                         width=1, border_radius=h // 2)
        for i in range(1, 5):
            tick_x = x + int(w * i / 5)
            pygame.draw.line(self.canvas, (7, 12, 18), (tick_x, y + 1),
                             (tick_x, y + h - 1), 1)

    # ------------------------------------------------------------------
    # Panel de monitoreo
    # ------------------------------------------------------------------
    def draw_panel(self, game) -> None:
        px, py, pw, ph = config.PANEL_RECT
        self.panel(pygame.Rect(px, py, pw, ph), config.COL_PANEL,
                   config.COL_PANEL_EDGE, radius=14)
        self._draw_tabs(game, px, py, pw)
        agent = game.panel_agent()

        is_bot = isinstance(agent, PlayerBot)
        if is_bot:
            self._draw_bot_panel(game, agent, px, py, pw)
        else:
            self._draw_agent_panel(game, agent, px, py, pw)

    def _draw_tabs(self, game, px: int, py: int, pw: int) -> None:
        tabs = [
            ("ARGOS", config.COL_RED, 0),
            ("DRON-1", config.COL_CYAN, 1),
            ("DRON-2", config.COL_PURPLE, 2),
            ("ÍCARO", config.COL_GREEN, 3),
        ]
        x = px + 14
        y = py + 12
        width = (pw - 28 - 3 * 5) // 4
        for label, color, index in tabs:
            rect = pygame.Rect(x, y, width, 28)
            selected = game.panel_index == index
            fill = (19, 31, 45) if selected else (12, 20, 31)
            pygame.draw.rect(self.canvas, fill, rect, border_radius=6)
            border = color if selected else (28, 44, 60)
            pygame.draw.rect(self.canvas, border, rect, width=1, border_radius=6)
            if selected:
                pygame.draw.line(self.canvas, color, (rect.x + 8, rect.bottom - 1),
                                 (rect.right - 8, rect.bottom - 1), 2)
            self.text(label, rect.centerx, rect.centery, 10,
                      color if selected else config.COL_MUTED, bold=True,
                      anchor="center")
            x += width + 5

    def _draw_agent_panel(self, game, agent, px: int, py: int, pw: int) -> None:
        x0 = px + 16
        content_w = pw - 32
        color = getattr(agent, "color", config.COL_CYAN)

        self.text(agent.name, x0, py + 50, 21, color, bold=True)
        self.text(agent.role.upper(), x0 + content_w, py + 56, 8,
                  config.COL_DIM, anchor="topright")
        self.text(agent.state, x0, py + 76, 12, self.state_color(agent.state), bold=True)

        # Estado y objetivo.
        self._micro_label("OBJETIVO", x0, py + 98)
        goal_text = agent.target_label or "—"
        self.text(self.fit_text(goal_text, 13, 238), x0, py + 111, 13,
                  config.COL_TEXT)
        self._micro_label("ALGORITMO", x0 + 265, py + 98)
        self.text(agent.algorithm_used(), x0 + 265, py + 111, 13,
                  config.COL_CYAN if agent.algorithm_used() == "A*" else config.COL_AMBER,
                  bold=True)
        self.text("h Manhattan" if agent.algorithm_used() == "A*" else "sin heurística",
                  x0 + 330, py + 112, 9, config.COL_DIM)

        # Percepción y memoria.
        self._micro_label("PERCEPCIÓN", x0, py + 136)
        self._wrapped_block(agent.perception_text(game), x0, py + 149,
                            content_w, 11, config.COL_MUTED, 2)
        self._micro_label("MEMORIA / CONTEXTO", x0, py + 183)
        self._wrapped_block(agent.memory_text(game), x0, py + 196,
                            content_w, 11, config.COL_MUTED, 2)

        self.hline(x0, px + pw - 16, py + 228, config.COL_PANEL_EDGE)
        self.text("BÚSQUEDA", x0, py + 236, 9, config.COL_DIM, bold=True)
        result = agent.last_search
        self.text(f"salida {fmt(agent.goal)}", x0 + content_w, py + 236, 9,
                  config.COL_DIM, anchor="topright")

        self._draw_metrics(x0, py + 254, result)
        algorithm_note = (
            "h = Manhattan · admisible y consistente" if result and result.algorithm == "astar"
            else "sin heurística · coste mínimo garantizado" if result
            else "sin búsqueda ejecutada todavía"
        )
        self.text(algorithm_note, x0, py + 302, 9, config.COL_DIM)

        self.text("COMPARACIÓN · MISMO ORIGEN Y DESTINO", x0, py + 322, 9,
                  config.COL_DIM, bold=True)
        self._draw_comparison(x0, py + 338, content_w, agent)

        # Bloque específico del agente.
        self._draw_specific(game, agent, x0, py + 421, content_w)
        self.hline(x0, px + pw - 16, py + 469, config.COL_PANEL_EDGE)
        self._draw_log(game, x0, py + 476, content_w, py + 648)
        self._draw_panel_footer(px, py, pw, config.PANEL_RECT[3])

    def _draw_bot_panel(self, game, bot: PlayerBot, px: int, py: int, pw: int) -> None:
        x0 = px + 16
        content_w = pw - 32
        color = config.COL_GREEN if not game.autopilot else config.COL_CYAN
        self.text("ÍCARO", x0, py + 50, 21, color, bold=True)
        self.text("PILOTO AUTOMÁTICO" if game.autopilot else "CONTROL MANUAL",
                  x0 + content_w, py + 56, 8, config.COL_DIM, anchor="topright")
        state = bot.state if game.autopilot else "CONTROL MANUAL"
        self.text(state, x0, py + 76, 12, self.state_color(state), bold=True)

        self._micro_label("OBJETIVO", x0, py + 98)
        if game.autopilot:
            target = bot.target_label
        else:
            remaining = len(game.remaining_cards)
            target = (f"{remaining} tarjeta(s) · salida" if remaining
                      else "salida de emergencia")
        self.text(self.fit_text(target, 13, 250), x0, py + 111, 13, config.COL_TEXT)
        self._micro_label("POSICIÓN", x0 + 280, py + 98)
        self.text(fmt(game.player.tile), x0 + 280, py + 111, 13, config.COL_TEXT,
                  mono=True)
        self.text("A*" if game.algorithm == "astar" else "Dijkstra",
                  x0 + 365, py + 111, 13, config.COL_CYAN, bold=True)

        self._micro_label("PERCEPCIÓN", x0, py + 136)
        self._wrapped_block(
            bot.perception_text(game), x0, py + 149, content_w, 11,
            config.COL_MUTED, 2,
        )
        self._micro_label("MEMORIA / CONTEXTO", x0, py + 183)
        self._wrapped_block(
            bot.memory_text(game) if game.autopilot
            else f"pasos {game.player.steps} · terminales {len(game.used_terminals)}/{len(game.maze.terminals)} · piloto apagado",
            x0, py + 196, content_w, 11, config.COL_MUTED, 2,
        )

        self.hline(x0, px + pw - 16, py + 228, config.COL_PANEL_EDGE)
        self.text("BÚSQUEDA DEL PILOTO", x0, py + 236, 9, config.COL_DIM, bold=True)
        result = bot.last_search if (game.autopilot or bot.last_search) else None
        self.text(f"salida {fmt(bot.goal)}" if bot.goal else "sin plan activo",
                  x0 + content_w, py + 236, 9, config.COL_DIM, anchor="topright")
        self._draw_metrics(x0, py + 254, result)
        note = (
            "coste con evasión de ARGOS · riesgo penalizado"
            if result else "activa con P para observar la planificación"
        )
        self.text(note, x0, py + 302, 9, config.COL_DIM)
        self.text("COMPARACIÓN · MISMO ORIGEN Y DESTINO", x0, py + 322, 9,
                  config.COL_DIM, bold=True)
        self._draw_comparison(x0, py + 338, content_w, bot)

        self.text("DECISIÓN DEL PILOTO", x0, py + 421, 9, config.COL_DIM, bold=True)
        if game.autopilot:
            self._wrapped_block(
                "Planifica hacia tarjetas/salida y penaliza el radio de ARGOS y su "
                "intercepción prevista.",
                x0, py + 436, content_w, 11, config.COL_MUTED, 2,
            )
        else:
            self._wrapped_block(
                "Control manual. Pulsa P para ceder el control al agente y ver sus "
                "métricas de búsqueda en este panel.",
                x0, py + 436, content_w, 11, config.COL_MUTED, 2,
            )
        self.hline(x0, px + pw - 16, py + 469, config.COL_PANEL_EDGE)
        self._draw_log(game, x0, py + 476, content_w, py + 648)
        self._draw_panel_footer(px, py, pw, config.PANEL_RECT[3])

    def _draw_metrics(self, x: int, y: int, result) -> None:
        labels = [("COSTE", x), ("EXPANDIDOS", x + 96), ("TIEMPO", x + 204),
                  ("RUTA", x + 315)]
        values = [
            (f"{result.cost:g}" if result and result.found else "—"),
            (str(result.expanded) if result else "—"),
            (f"{result.elapsed_ms:.2f} ms" if result else "—"),
            (f"{len(result.path) - 1} pasos" if result and result.found else "—"),
        ]
        colors = [config.COL_TEXT, config.COL_TEXT, config.COL_TEXT, config.COL_MUTED]
        for (label, lx), value, color in zip(labels, values, colors):
            self._micro_label(label, lx, y)
            self.text(value, lx, y + 13, 14 if "pasos" not in value else 11,
                      color, bold="pasos" not in value, mono="pasos" not in value)
        if result:
            self.text(
                f"frontera máx. {result.frontier_peak} · generados {result.generated}"
                + (f" · reaperturas {result.reopenings}" if result.reopenings else ""),
                x, y + 33, 8, config.COL_DIM,
            )

    def _draw_comparison(self, x: int, y: int, width: int, agent) -> None:
        d_res = getattr(agent, "last_dijkstra", None)
        a_res = getattr(agent, "last_astar", None)
        chosen = getattr(agent, "last_search", None)
        if d_res is None and a_res is None:
            self.text("Sin datos aún: el agente todavía no ha planificado.",
                      x, y + 14, 10, config.COL_DIM)
            return
        nodes = [
            d_res.expanded if d_res and d_res.found else 0,
            a_res.expanded if a_res and a_res.found else 0,
        ]
        max_nodes = max(1, max(nodes))
        rows = [
            ("Dijkstra", d_res, config.COL_AMBER),
            ("A*", a_res, config.COL_CYAN),
        ]
        for i, (label, result, color) in enumerate(rows):
            row_y = y + i * 24
            row_rect = pygame.Rect(x, row_y, width, 21)
            pygame.draw.rect(self.canvas, (12, 21, 32), row_rect, border_radius=4)
            if result and result.found:
                bar_w = max(4, int((width - 2) * result.expanded / max_nodes))
                bar = pygame.Surface((bar_w, 21), pygame.SRCALPHA)
                pygame.draw.rect(bar, (*color, 22), pygame.Rect(0, 0, bar_w, 21),
                                 border_radius=4)
                self.canvas.blit(bar, (x, row_y))
            active = chosen is not None and chosen.algorithm == (
                "dijkstra" if i == 0 else "astar"
            )
            pygame.draw.circle(self.canvas, color if active else (50, 70, 86),
                               (x + 8, row_y + 10), 2)
            self.text(label, x + 16, row_y + 5, 10,
                      color if active else config.COL_MUTED, bold=active)
            if result:
                cost = f"{result.cost:g}" if result.found else "sin ruta"
                self.text(cost, x + 100, row_y + 5, 10, config.COL_TEXT)
                self.text(f"{result.expanded}", x + 168, row_y + 5, 10,
                          config.COL_TEXT)
                self.text(f"{result.elapsed_ms:.2f} ms", x + 236, row_y + 5, 10,
                          config.COL_MUTED)
                self.text("ACTIVO" if active else "", x + width - 4, row_y + 5,
                          8, color, bold=True, anchor="topright")
        if d_res and a_res and d_res.found and a_res.found:
            saved = 0.0
            if d_res.expanded > 0:
                saved = 100 * (1 - a_res.expanded / d_res.expanded)
            same_cost = abs(d_res.cost - a_res.cost) <= 1e-9
            optimality = "Óptimo igualado" if same_cost else "COSTES DISTINTOS"
            text = (
                f"{optimality} · A* expande {saved:+.0f}% nodos · "
                f"coste {a_res.cost:g}"
            )
            self.text(text, x, y + 50, 9,
                      config.COL_MUTED if same_cost else config.COL_RED)

    def _draw_specific(self, game, agent, x: int, y: int, width: int) -> None:
        if hasattr(agent, "prediction"):
            self._micro_label("PREDICCIÓN RECURSIVA", x, y)
            if agent.prediction:
                p = agent.prediction
                self.text(
                    f"d={p.depth} · {p.nodes} nodos · {p.leaves} hojas · "
                    f"{p.elapsed_ms:.2f} ms" + (" · podado" if p.truncated else ""),
                    x, y + 13, 10, config.COL_TEXT,
                    max_width=width,
                )
                self.text(
                    f"probable {fmt(p.probable)} → intercepta {fmt(p.target)}",
                    x, y + 27, 10, config.COL_PURPLE, max_width=width,
                )
            else:
                self.text("sin contacto visual: la memoria guía la investigación",
                          x, y + 13, 10, config.COL_DIM)
        elif hasattr(agent, "route"):
            self._micro_label("PATRULLA DE SECTOR", x, y)
            route = " → ".join(fmt(t) for t in agent.route)
            self.text(route, x, y + 13, 10, config.COL_TEXT, max_width=width)
            self.text(
                f"reportes enviados {agent.reports} · último reporte hace "
                f"{max(0.0, game.time - agent.last_report_at):.0f}s",
                x, y + 27, 9, config.COL_DIM,
            )
        else:
            self._micro_label("DECISIÓN DEL PILOTO", x, y)
            self.text("Penaliza el radio de ARGOS y su intercepción prevista.",
                      x, y + 13, 10, config.COL_DIM)

    def _draw_log(self, game, x: int, y: int, width: int, bottom: int) -> None:
        self.text("REGISTRO DE EVENTOS · TIEMPO REAL", x, y, 9,
                  config.COL_DIM, bold=True)
        self.text(f"{len(game.log)} eventos", x + width, y, 8,
                  config.COL_DIM, anchor="topright")
        line_height = 15
        available = max(1, (bottom - (y + 15)) // line_height)
        entries = list(game.log)[-min(12, available):]
        for index, entry in enumerate(entries):
            row_y = y + 17 + index * line_height
            color = LOG_COLORS.get(entry.category, config.COL_TEXT)
            pygame.draw.circle(self.canvas, color, (x + 4, row_y + 6), 2)
            self.text(self.clock_text(entry.time), x + 13, row_y, 8,
                      config.COL_DIM, mono=True)
            speaker = entry.speaker[:6]
            self.text(speaker, x + 45, row_y, 8, color, bold=True)
            text_x = x + 96
            max_width = width - 96
            self.text(entry.text, text_x, row_y, 8, config.COL_TEXT,
                      max_width=max_width)

    def _draw_panel_footer(self, px: int, py: int, pw: int, ph: int) -> None:
        self.hline(px + 16, px + pw - 16, py + ph - 34, config.COL_PANEL_EDGE)
        self.text("TAB agente · 1-4 panel · F1 A*/Dijkstra · F2 rutas", px + 16,
                  py + ph - 27, 8, config.COL_DIM)
        self.text("F5 bloqueo · F6 alarma · P piloto", px + pw - 16,
                  py + ph - 27, 8, config.COL_DIM, anchor="topright")

    def _micro_label(self, text: str, x: int, y: int) -> None:
        self.text(text, x, y, 8, config.COL_DIM, bold=True)

    def _wrapped_block(self, text: str, x: int, y: int, width: int, size: int,
                       color, max_lines: int) -> None:
        lines = self.wrapped_lines(text, size, width, max_lines)
        for index, line in enumerate(lines):
            self.text(line, x, y + index * (size + 2), size, color)

    # ------------------------------------------------------------------
    # Pie
    # ------------------------------------------------------------------
    def draw_footer(self, game, fps: float) -> None:
        pygame.draw.line(self.canvas, (18, 30, 43), (0, 760), (self.width, 760))
        controls = (
            "WASD mover · E hackear · H operador · P piloto IA · TAB panel · F1 A*/Dijkstra · "
            "F2 rutas · F5 bloqueo · F6 alarma · R reiniciar · ESC pausa"
        )
        self.text(controls, 16, 766, 9, config.COL_DIM, max_width=1120)
        self.text(f"{fps:.0f} FPS", self.width - 16, 766, 9, config.COL_DIM,
                  anchor="topright")
        latest = game.log[-1] if game.log else None
        if latest:
            color = LOG_COLORS.get(latest.category, config.COL_TEXT)
            prefix = f"[{self.clock_text(latest.time)}] {latest.speaker}: "
            self.text(prefix, 16, 782, 9, color, bold=True)
            prefix_width = self.text_width(prefix, 9, bold=True)
            self.text(latest.text, 16 + prefix_width, 782, 9, config.COL_MUTED,
                      max_width=1040 - prefix_width)
        algo = "A*" if game.algorithm == config.ALGO_ASTAR else "Dijkstra"
        self.text(f"SEMILLA {game.seed} · {algo} · {game.maze.size_label}",
                  self.width - 16, 782, 9, config.COL_DIM, anchor="topright")
