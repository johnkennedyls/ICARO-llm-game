from .screens import ScreensMixin
from .ui import UIMixin
from .world import WorldMixin


class Renderer(ScreensMixin, UIMixin, WorldMixin):
    pass
