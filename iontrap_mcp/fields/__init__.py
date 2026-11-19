"""Electrostatic field evaluation for IonTrapClaw (first-kind BEM).

Public API
----------
* :func:`discretize` — split an electrode into panel centroids/areas (um).
* :class:`BEMSolver` — panel assembly, cached LU solve, potential/field.
* :class:`TrapAnalyzer` — RF null, pseudopotential, secular frequencies.
* :func:`solve_dc_voltages` — least-squares DC voltage synthesis.
* :func:`shuttle_waveform` — voltage waveforms for ion shuttling.
"""

from .bem import BEMSolver, discretize, UM_TO_M, EPS0
from .trap import TrapAnalyzer, QE, AMU
from .solve import solve_dc_voltages, shuttle_waveform

__all__ = [
    "discretize",
    "BEMSolver",
    "TrapAnalyzer",
    "solve_dc_voltages",
    "shuttle_waveform",
    "UM_TO_M",
    "EPS0",
    "QE",
    "AMU",
]
