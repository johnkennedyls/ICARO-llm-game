"""Script interno de balance: simula partidas con piloto automático."""
from icaro.game import Game

for seed in [1, 2, 3, 4, 5, 7, 11, 42]:
    g = Game(seed=seed, write_log=False)
    g.toggle_autopilot()
    while g.state == "playing" and g.time < 180:
        g.update(1 / 30)
    blocks = g.stats["blocks"]
    print(
        f"seed={seed:3d} state={g.state:6s} t={g.time:6.1f}s "
        f"cards={len(g.player.cards)} energy={g.player.energy:5.1f} "
        f"blocks={blocks} argos={g.argos.state} searches={g.stats['searches']} "
        f"reason={g.end_reason[:38]}"
    )
    g.close()
