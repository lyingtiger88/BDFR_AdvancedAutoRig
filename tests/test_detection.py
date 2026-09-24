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
for i in (0, 1, 4): parts[i].wheel_axle = 'REAR'
for i in (2, 3): parts[i].wheel_axle = 'FRONT'
assert rig.wheel_labels(parts, settings) == {0:'RL', 1:'RR', 2:'FL', 3:'FR', 4:'RL'}
for p in parts: p.wheel_axle = 'AUTO'
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
parts2[0].wheel_axle, parts2[1].wheel_axle = 'REAR', 'FRONT'
assert rig.wheel_labels(parts2, settings) == {0:'Rear', 1:'Front'}
settings.vehicle_type = 'AIRPLANE'
settings.bounds_min, settings.bounds_max = (-4,-3,0), (4,3,2.5)
plane_wheels = [
    NS(**vars(mkpart((0,2,.35),(-.1,1.8,0),(.1,2.2,.7))), source=NS(name='NoseWheel')),
    NS(**vars(mkpart((-1,-1,.35),(-1.1,-1.2,0),(-.9,-.8,.7))), source=NS(name='MainWheel_L')),
    NS(**vars(mkpart((1,-1,.35),(.9,-1.2,0),(1.1,-.8,.7))), source=NS(name='MainWheel_R')),
]
plane_labels = rig.wheel_labels(plane_wheels, settings)
assert len(set(plane_labels.values())) == 3
assert rig.steering_labels(plane_wheels, settings, plane_labels) == {plane_labels[0]}
plane_wheels[0].wheel_steer = 'NO'
assert rig.steering_labels(plane_wheels, settings, plane_labels) == set()
plane_wheels[1].wheel_steer = 'YES'
assert rig.steering_labels(plane_wheels, settings, plane_labels) == {plane_labels[1]}
plane_wheels[0].wheel_steer, plane_wheels[1].wheel_steer = 'AUTO', 'AUTO'
plane_parts = plane_wheels + [NS(kind=k) for k in ('PROPELLER','AILERON','AILERON',
                                                   'ELEVATOR','RUDDER','FLAP')]
settings.rig_mode, settings.bone_count = 'SIMPLE', 2
assert rig.rig_bone_plan(plane_parts, settings)[2:] == (7, 7)
settings.rig_mode, settings.bone_count = 'ADVANCED', 20
assert rig.rig_bone_plan(plane_parts, settings)[2:] == (15, 20)
for name, expected in [('NoseWheel', 'WHEEL'), ('MainWheel_L', 'WHEEL'),
                       ('NoseGear', 'GEAR'), ('MainStrut_R', 'GEAR'),
                       ('Propeller_1', 'PROPELLER'), ('Aileron_L', 'AILERON'),
                       ('Elevator', 'ELEVATOR'), ('Rudder', 'RUDDER'), ('Flap_L', 'FLAP')]:
    assert rig.name_hint(NS(name=name, get=lambda key, default=None: default),
                         'AIRPLANE') == expected, name
assert rig.name_hint(NS(name='Aileron_L', get=lambda key, default=None: default),
                     'CAR') is None
mesh = NS(vertices=[NS(co=V((i,0,0))) for i in range(6)],
          edges=[NS(vertices=(0,1)),NS(vertices=(1,2)),
                 NS(vertices=(3,4)),NS(vertices=(4,5))])
obj = NS(data=mesh)
assert rig.components(obj, True, 1000) == [[0,1,2],[3,4,5]]
print('PASS: vehicle and aircraft classification, steering overrides, islands and bone budgets')
