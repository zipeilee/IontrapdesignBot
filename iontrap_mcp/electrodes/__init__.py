"""Parameterized electrode-geometry generators for IonTrapClaw.

All generators return :class:`iontrap_mcp.common.ElectrodeSet` and work
in micrometres with the trap axis along x and electrodes in z = 0.
"""

from .surface import five_wire
from .junction import x_junction, t_junction
from .threed import two_layer
from .racetrack import racetrack
from .routing import fanout

__all__ = ["five_wire", "x_junction", "t_junction", "two_layer", "racetrack", "fanout"]
