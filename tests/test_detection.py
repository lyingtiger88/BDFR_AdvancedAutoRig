"""Smoke checks of geometry detection independent of a Blender binary."""
import importlib.util
import math
import sys
import types
from types import SimpleNamespace as NS

class V:
    def __init__(self, seq): self.a = tuple(float(v) for v in seq)
    def __getitem__(self, i): return self.a[i]
    def __iter__(self): return iter(self.a)
    def __add__(self, o): return V(x+y for x, y in zip(self, o))
    def __sub__(self, o): return V(x-y for x, y in zip(self, o))
    def __mul__(self, x): return V(y*x for y in self)
    __rmul__ = __mul__
    def __truediv__(self, x): return self * (1/x)
    def dot(self, o): return sum(x*y for x,y in zip(self,o))
    @property
    def length(self): return math.sqrt(self.dot(self))
    @property
    def x(self): return self[0]
    @property
    def y(self): return self[1]
    @property
    def z(self): return self[2]
    def __repr__(self): return repr(self.a)

bpy = types.ModuleType('bpy')
props = types.ModuleType('bpy.props')
for name in ['BoolProperty','CollectionProperty','EnumProperty','FloatProperty',
             'IntProperty','PointerProperty','StringProperty','FloatVectorProperty']:
    setattr(props, name, lambda **kwargs: None)
bpy.props = props
bpy.types = NS(PropertyGroup=type('PropertyGroup', (), {}), Operator=type('Operator', (), {}),
               Panel=type('Panel', (), {}), Object=type('Object', (), {}))
sys.modules['bpy'] = bpy
sys.modules['bpy.props'] = props
mathutils = types.ModuleType('mathutils'); mathutils.Vector = V
sys.modules['mathutils'] = mathutils
spec = importlib.util.spec_from_file_location('vehicle_auto_rig', str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'vehicle_auto_rig' / '__init__.py'))
rig = importlib.util.module_from_spec(spec); spec.loader.exec_module(rig)

settings = NS(forward_axis='Y', forward_sign='PLUS', vehicle_type='CAR',
              bounds_min=(-1,-2,0), bounds_max=(1,2,2))
mkpart = lambda center, lo, hi: NS(kind='WHEEL', center=center, minimum=lo, maximum=hi)
parts = [
    mkpart((-.8,1.2,.4),(-1, .8,0),(-.6,1.6,.8)),
    mkpart((.8,1.2,.4),(.6, .8,0),(1,1.6,.8)),
    mkpart((-.8,-1.2,.4),(-1,-1.6,0),(-.6,-.8,.8)),
    mkpart((.8,-1.2,.4),(.6,-1.6,0),(1,-.8,.8)),
    mkpart((-.8,1.2,.4),(-.85,1.0,.2),(-.75,1.4,.6)),
]
labels = rig.wheel_labels(parts, settings)
assert labels == {0:'FL', 1:'FR', 2:'RL', 3:'RR', 4:'FL'}, labels
settings.rig_mode, settings.bone_count = 'ADVANCED', 17
_, segments, required, actual = rig.rig_bone_plan(parts, settings)
assert required == 12 and actual == 17 and sum(segments.values()) == 9
settings.rig_mode, settings.bone_count = 'SIMPLE', 3
assert rig.rig_bone_plan(parts, settings)[2:] == (8, 8)
assert rig.classify(NS(name='mesh', get=lambda key, default=None: default),
                    V((-.99, .8, 0)), V((-.61,1.6,.8)),
                    V(settings.bounds_min), V(settings.bounds_max), settings, 1)[0] == 'WHEEL'
settings.vehicle_type = 'MOTORCYCLE'
settings.bounds_min = (-.5,-1,0); settings.bounds_max = (.5,1,1.5)
parts2 = [mkpart((0,.75,.35),(-.08,.40,0),(.08,1.1,.7)),
          mkpart((0,-.75,.35),(-.08,-1.1,0),(.08,-.4,.7))]
assert rig.wheel_labels(parts2, settings) == {0:'Front', 1:'Rear'}
mesh = NS(vertices=[NS(co=V((i,0,0))) for i in range(6)],
          edges=[NS(vertices=(0,1)),NS(vertices=(1,2)),
                 NS(vertices=(3,4)),NS(vertices=(4,5))])
obj = NS(data=mesh)
assert rig.components(obj, True, 1000) == [[0,1,2],[3,4,5]]
print('PASS: classification, wheels, islands and simple/advanced bone budgets')
