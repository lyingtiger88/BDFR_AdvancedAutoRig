"""Script-only Maya core for BDFR Advanced AutoRig; no UI or Maya import at load."""

from .core import Analysis, Joint, Options, Part, Plan, analyze, plan_rig
from .scene import (BuiltRig, DRIVECORE_WHEEL_NAMES, analyze_selection,
                    build_rig, drivecore_wheel_bones)
from .export import ENGINE_AXES, ExportOptions, ExportResult, export_game_fbx, forward_correction

__all__ = ['Analysis', 'Joint', 'Options', 'Part', 'Plan', 'BuiltRig',
           'analyze', 'plan_rig', 'analyze_selection', 'build_rig',
           'ENGINE_AXES', 'ExportOptions', 'ExportResult', 'export_game_fbx', 'forward_correction',
           'DRIVECORE_WHEEL_NAMES', 'drivecore_wheel_bones']
