#!/usr/bin/env python
"""Punto de entrada de El escape de Ícaro.

Ejemplos:
    python main.py
    python main.py --seed 42 --start
    python main.py --cells 21 14 --start --autopilot
"""

from __future__ import annotations

import argparse

from icaro import config
from icaro.app import run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="El escape de Ícaro · laberinto de supervivencia con agentes IA"
    )
    parser.add_argument("--seed", type=int, default=config.DEFAULT_SEED,
                        help="semilla del mapa (reproducible)")
    parser.add_argument("--cells", type=int, nargs=2, metavar=("X", "Y"),
                        default=(config.DEFAULT_CELLS_X, config.DEFAULT_CELLS_Y),
                        help="dimensiones del generador en celdas (por defecto 17 12)")
    parser.add_argument("--start", action="store_true",
                        help="omitir la pantalla de título")
    parser.add_argument("--autopilot", action="store_true",
                        help="empezar con el piloto automático de Ícaro")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(seed=args.seed, cells_x=args.cells[0], cells_y=args.cells[1],
        start=args.start, autopilot=args.autopilot)
