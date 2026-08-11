import random
from uuid import UUID, uuid4

from geometry import Tuple4

from positionpolling.const import Y_RANGE, World
from positionpolling.models import Entry
from positionpolling.util import coerce


def gen_pos_logs(
        n: int,
        *,
        players: list[UUID | str] | int = 5,
        worlds: list[World] | None = None,
        bounds: Tuple4[int] = (-2000, -2000, 2000, 2000),
    ) -> list[Entry]:
    """Generates a list of ``n`` ``Entry`` objects."""
    worlds = worlds or list(World)
    playerlist = [coerce(p, UUID) for p in players] if isinstance(players, list) else [uuid4() for _ in range(players)]

    return [
        Entry(
            t,
            random.choice(playerlist),
            world := random.choice(worlds),
            random.randint(bounds[0], bounds[2]),
            random.randint(*Y_RANGE[world]),
            random.randint(bounds[1], bounds[3]),
        )
        for t in range(n)
    ]
