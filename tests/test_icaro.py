from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from icaro import config
from icaro.algorithms import astar, dijkstra, heuristic_is_consistent
from icaro.app import App
from icaro.experiments import run_experiments
from icaro.game import Game
from icaro.graph import GridGraph
from icaro.maze import Maze
from icaro.planning import predict_intercept
from icaro.render import Renderer


def path_cost(graph: GridGraph, path: list[tuple[int, int]]) -> float:
    return sum(graph.tile_cost(tile) for tile in path[1:])


class AlgorithmTests(unittest.TestCase):
    def test_weighted_path_prefers_cheaper_detour(self) -> None:
        tiles = {(x, y) for y in range(2) for x in range(3)}
        costs = {tile: 1.0 for tile in tiles}
        costs[(1, 0)] = 10.0
        graph = GridGraph(tiles, costs)

        for search in (dijkstra(graph, (0, 0), (2, 0)),
                       astar(graph, (0, 0), (2, 0))):
            self.assertTrue(search.found)
            self.assertEqual(search.cost, 4.0)
            self.assertEqual(search.path, [(0, 0), (0, 1), (1, 1), (2, 1), (2, 0)])
            self.assertEqual(path_cost(graph, search.path), search.cost)

    def test_dijkstra_and_astar_match_on_generated_maps(self) -> None:
        for seed in (1, 7, 42):
            for cells in ((6, 5), (10, 7)):
                maze = Maze(cells_x=cells[0], cells_y=cells[1], seed=seed)
                goals = {maze.exit, *maze.cards}
                d_result = dijkstra(maze.graph, maze.start, goals)
                a_result = astar(maze.graph, maze.start, goals)
                self.assertTrue(d_result.found)
                self.assertTrue(a_result.found)
                self.assertAlmostEqual(d_result.cost, a_result.cost)
                self.assertTrue(heuristic_is_consistent(maze.graph, goals))

    def test_unreachable_goal_returns_failure(self) -> None:
        graph = GridGraph({(0, 0), (1, 0)}, {})
        result = astar(graph, (0, 0), (3, 0))
        self.assertFalse(result.found)
        self.assertEqual(result.path, [])
        self.assertEqual(result.goal, None)


class GraphTests(unittest.TestCase):
    def test_blocked_tile_is_removed_from_navigation_and_metrics(self) -> None:
        graph = GridGraph({(0, 0), (1, 0), (2, 0)}, {})
        self.assertEqual((graph.vertices, graph.edges), (3, 2))
        graph.set_blocked((1, 0))

        self.assertEqual((graph.vertices, graph.edges), (2, 0))
        self.assertEqual(graph.reachable((0, 0)), {(0, 0)})
        self.assertEqual(graph.distance_map((0, 0)), {(0, 0): 0})
        self.assertFalse(graph.line_of_sight((0, 0), (2, 0)))


class MazeTests(unittest.TestCase):
    def test_generation_is_deterministic_and_playable(self) -> None:
        first = Maze(cells_x=10, cells_y=7, seed=7)
        second = Maze(cells_x=10, cells_y=7, seed=7)
        self.assertEqual(first.open_tiles, second.open_tiles)
        self.assertEqual(first.cards, second.cards)
        self.assertEqual(first.doors, second.doors)
        self.assertEqual(len(first.cards), config.CARD_COUNT)
        self.assertTrue({first.exit, *first.cards}.issubset(first.graph.reachable(first.start)))


class PlanningTests(unittest.TestCase):
    def test_recursive_prediction_is_bounded(self) -> None:
        maze = Maze(cells_x=6, cells_y=5, seed=7)
        result = predict_intercept(
            maze, maze.argos_start, maze.start, [maze.exit], depth=3, node_budget=5
        )
        self.assertLessEqual(result.nodes, 5)
        self.assertLessEqual(result.depth, 3)
        self.assertIsNotNone(result.target)

    def test_zero_depth_uses_current_position(self) -> None:
        maze = Maze(cells_x=6, cells_y=5, seed=7)
        result = predict_intercept(
            maze, maze.argos_start, maze.start, [maze.exit], depth=0
        )
        self.assertEqual(result.target, maze.start)
        self.assertEqual(result.nodes, 0)


class GameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(seed=7, write_log=False)

    def tearDown(self) -> None:
        self.game.close()

    def move_to_exit(self) -> None:
        x, y = self.game.maze.exit
        neighbors = [(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        start = next(tile for tile in neighbors if self.game.maze.can_enter(tile))
        self.game.player.tile = start
        self.game.player.step_timer = 0.0
        direction = (self.game.maze.exit[0] - start[0], self.game.maze.exit[1] - start[1])
        self.game.attempt_player_move(direction)

    def test_exit_requires_three_cards(self) -> None:
        self.move_to_exit()
        self.assertEqual(self.game.state, "playing")
        self.assertEqual(self.game.player.cards, set())

    def test_exit_opens_after_three_cards(self) -> None:
        self.game.player.cards = set(self.game.maze.cards)
        self.move_to_exit()
        self.assertEqual(self.game.state, "won")

    def test_time_limit_loses_match(self) -> None:
        self.game.time = config.TIME_LIMIT - 0.05
        self.game.update(0.1)
        self.assertEqual(self.game.state, "lost")
        self.assertEqual(self.game.time, config.TIME_LIMIT)
        self.assertIn("tiempo", self.game.end_reason.lower())

    def test_empty_energy_prevents_movement(self) -> None:
        self.game.player.energy = 0.0
        moved = self.game.attempt_player_move((1, 0))
        self.assertFalse(moved)
        self.assertEqual(self.game.state, "lost")
        self.assertIn("energía", self.game.end_reason.lower())

    def test_hazard_can_exhaust_energy_before_collecting_card(self) -> None:
        hazard = next(iter(self.game.maze.hazards))
        x, y = hazard
        neighbors = [(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        start = next(tile for tile in neighbors if self.game.maze.can_enter(tile))
        self.game.player.tile = start
        self.game.player.energy = config.HAZARD_ENERGY_PENALTY / 2
        self.game.player.step_timer = 0.0
        direction = (hazard[0] - start[0], hazard[1] - start[1])
        self.game.attempt_player_move(direction)
        self.assertEqual(self.game.state, "lost")
        self.assertEqual(self.game.player.energy, 0.0)

    def test_blockade_has_valid_more_expensive_alternative(self) -> None:
        result = self.game.force_blockade()
        self.assertIsNotNone(result)
        self.assertGreater(result["after"], result["before"])
        self.assertTrue(self.game.maze.is_locked(result["door"]))
        alternative = dijkstra(self.game.maze.graph, self.game.player.tile,
                               self.game.player_objectives())
        self.assertTrue(alternative.found)
        self.assertNotIn(result["door"], alternative.path)
        self.game.maze.unlock_expired(result["time"] + result["duration"] + 0.1)
        self.assertFalse(self.game.maze.is_locked(result["door"]))

    def test_drone_report_updates_argos_memory(self) -> None:
        drone = self.game.drones[0]
        x, y = self.game.player.tile
        drone.tile = (x + 1, y)
        drone.last_report_at = -999.0
        drone.think(self.game)
        self.assertEqual(drone.reports, 1)
        self.assertEqual(self.game.argos.last_seen, self.game.player.tile)


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((config.WINDOW_W, config.WINDOW_H))
        cls.canvas = pygame.Surface((config.WINDOW_W, config.WINDOW_H)).convert()
        cls.renderer = Renderer(cls.canvas)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_all_panels_and_screens_render(self) -> None:
        game = Game(seed=7, write_log=False)
        try:
            self.renderer.reset_fog()
            self.renderer.draw_title(7, config.DEFAULT_CELLS_X, config.DEFAULT_CELLS_Y, 60)
            game.toggle_autopilot()
            for _ in range(60):
                game.update(1 / 30)
                self.renderer.tick(1 / 30)
            for index in range(4):
                game.select_panel(index)
                self.renderer.draw_game(game, 60)
            self.renderer.draw_pause(game)
            for state, reason in (
                ("won", "Ícaro alcanzó la compuerta de emergencia"),
                ("lost", "La energía del traje se ha agotado"),
                ("lost", "El tiempo de emergencia se ha agotado"),
                ("lost", "ARGOS ha capturado a Ícaro"),
            ):
                game.state = state
                game.end_reason = reason
                self.renderer.draw_game(game, 60)
                self.renderer.draw_end(game)
        finally:
            game.close()

    def test_app_starts_pauses_and_restarts(self) -> None:
        app = App(seed=7, start=True)
        try:
            self.assertEqual(app.mode, "playing")
            app._handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
            self.assertEqual(app.mode, "paused")
            app._handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
            self.assertEqual(app.mode, "paused")
            app._handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
            self.assertEqual(app.mode, "playing")
            self.assertEqual(app.game.seed, 7)
            app._handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1))
            self.assertEqual(app.game.algorithm, config.ALGO_DIJKSTRA)
            app._draw()
        finally:
            app._close_game()
            pygame.quit()


class ExperimentTests(unittest.TestCase):
    def test_experiment_writes_reproducible_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            rows, csv_path, md_path = run_experiments(
                reps=1,
                seeds=[7],
                sizes=[("Pequeño", 6, 5)],
                out_dir=Path(folder),
            )
            self.assertEqual(len(rows), 6)
            self.assertTrue(csv_path.exists())
            self.assertTrue(md_path.exists())
            for scenario in ("salida", "tarjetas", "persecucion"):
                costs = [row["coste"] for row in rows if row["escenario"] == scenario]
                self.assertEqual(len(costs), 2)
                self.assertAlmostEqual(costs[0], costs[1])


if __name__ == "__main__":
    unittest.main()
