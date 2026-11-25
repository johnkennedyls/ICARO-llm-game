"""Capturas de desarrollo para revisar el acabado visual sin abrir la ventana."""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from icaro import config
from icaro.game import Game
from icaro.render import Renderer

OUT = os.path.join(os.path.dirname(__file__), "capturas")
os.makedirs(OUT, exist_ok=True)


def save(canvas, name):
    path = os.path.join(OUT, name)
    pygame.image.save(canvas, path)
    print("saved", path)


def main():
    pygame.init()
    pygame.display.set_mode((config.WINDOW_W, config.WINDOW_H))
    canvas = pygame.Surface((config.WINDOW_W, config.WINDOW_H)).convert()
    renderer = Renderer(canvas)
    renderer.tick(1 / 60)
    renderer.draw_title(7, config.DEFAULT_CELLS_X, config.DEFAULT_CELLS_Y, 60)
    save(canvas, "dev_title.png")

    game = Game(seed=7, write_log=False)
    game.toggle_autopilot()
    renderer.reset_fog()
    for _ in range(90):
        game.update(1 / 30)
        renderer.tick(1 / 30)
    renderer.draw_game(game, 60)
    save(canvas, "dev_game.png")

    renderer.draw_pause(game)
    save(canvas, "dev_pause.png")

    # Provoca un final para revisar la pantalla de resultados.
    game.state = "won"
    game.end_reason = "Ícaro alcanzó la compuerta de emergencia"
    game.end_time = game.time
    renderer.draw_game(game, 60)
    renderer.draw_end(game)
    save(canvas, "dev_end.png")

    game.close()
    pygame.quit()


if __name__ == "__main__":
    main()
