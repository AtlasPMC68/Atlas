"""Synthetic maps under a known deformation, for testing georeferencing.

Dev-only: nothing in the pipeline imports this package. The plan is in
``dev-docs/georeferencing-synthetic.md``.
"""

from .case import SyntheticCase, SyntheticMap
from .generate import (
    DEFORMATIONS,
    GENERATOR_VERSION,
    case_id,
    generate_case,
    generate_map,
    generate_twins,
    map_id,
)
from .regions import Rejected

__all__ = [
    "DEFORMATIONS",
    "GENERATOR_VERSION",
    "Rejected",
    "SyntheticCase",
    "SyntheticMap",
    "case_id",
    "generate_case",
    "generate_map",
    "generate_twins",
    "map_id",
]
