"""Maya-independent analysis and deterministic rig planning."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite, sqrt
import re


VEHICLES = frozenset({'CAR', 'TRUCK', 'MOTORCYCLE', 'BICYCLE', 'AIRPLANE'})
PARTS = frozenset({'BODY', 'WHEEL', 'DOOR', 'HOOD', 'TRUNK', 'PROPELLER',
                   'GEAR', 'AILERON', 'ELEVATOR', 'RUDDER', 'FLAP', 'IGNORE'})
SURFACES = frozenset({'AILERON', 'ELEVATOR', 'RUDDER', 'FLAP'})
AIRCRAFT_NAMES = (
    ('PROPELLER', r'propeller|\bprop\b|hélice|ملخ'),
    ('AILERON', r'aileron|شهپر'),
    ('ELEVATOR', r'elevator|stabilator|سکان افقی'),
    ('RUDDER', r'rudder|سکان عمودی'),
    ('FLAP', r'flap|فلپ'),
    ('GEAR', r'landing[_ .-]?gear|nose[_ .-]?gear|main[_ .-]?gear|tail[_ .-]?gear|strut'),
)
COMMON_NAMES = (
    ('WHEEL', r'wheel|tire|tyre|rim|چرخ|لاستیک'),
    ('DOOR', r'door|porte|در[ب]?'),
    ('HOOD', r'hood|bonnet|کاپوت'),
    ('TRUNK', r'trunk|boot|tailgate|صندوق'),
)


@dataclass(frozen=True)
class Options:
    vehicle: str = 'CAR'
    mode: str = 'SIMPLE'
    forward_axis: str = 'Y'  # world X/Y for Z-up; world X/Z for Y-up
    forward_sign: int = 1
    bone_count: int = 16
    up_axis: str = 'Z'
    front_wheels: int | None = None  # None: detect from geometry
    rear_wheels: int | None = None

    def __post_init__(self):
        if self.vehicle not in VEHICLES or self.mode not in {'SIMPLE', 'ADVANCED'}:
            raise ValueError('Unknown vehicle or rig mode')
        valid = {'X', 'Y'} if self.up_axis == 'Z' else {'X', 'Z'} if self.up_axis == 'Y' else set()
        if self.forward_axis not in valid or self.forward_sign not in {-1, 1}:
            raise ValueError('Forward axis must be horizontal in the chosen Y-up or Z-up scene')
        if not 2 <= self.bone_count <= 128:
            raise ValueError('bone_count must be between 2 and 128')
        for label, count in (('front_wheels', self.front_wheels),
                             ('rear_wheels', self.rear_wheels)):
            if count is not None and (type(count) is not int or not 0 <= count <= 32):
                raise ValueError(label + ' must be an integer between 0 and 32, or None')
        if self.mode != 'SIMPLE' and (self.front_wheels is not None or
                                      self.rear_wheels is not None):
            raise ValueError('front_wheels and rear_wheels are Simple-mode options')


@dataclass(frozen=True)
class Part:
    node: str
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    vertices: int
    kind: str = 'AUTO'
    axle: str = 'AUTO'
    steer: str = 'AUTO'
    shells: int = 1

    def __post_init__(self):
        if not self.node or self.kind not in PARTS | {'AUTO'}:
            raise ValueError('Invalid part name or type')
        if self.axle not in {'AUTO', 'FRONT', 'REAR'} or self.steer not in {'AUTO', 'YES', 'NO'}:
            raise ValueError('Invalid wheel override')
        if self.vertices < 1 or self.shells < 1 or len(self.minimum) != 3 or len(self.maximum) != 3:
            raise ValueError('Mesh must have vertices and three-dimensional bounds')
        if not all(isfinite(v) for v in (*self.minimum, *self.maximum)) or any(
                a > b for a, b in zip(self.minimum, self.maximum)) or all(
                a == b for a, b in zip(self.minimum, self.maximum)):
            raise ValueError('Degenerate or non-finite mesh bounds: ' + self.node)

    @property
    def center(self):
        return tuple((a + b) * .5 for a, b in zip(self.minimum, self.maximum))

    @property
    def size(self):
        return tuple(b - a for a, b in zip(self.minimum, self.maximum))


@dataclass(frozen=True)
class Analysis:
    options: Options
    parts: tuple[Part, ...]
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]


@dataclass(frozen=True)
class Joint:
    name: str
    parent: str | None
    position: tuple[float, float, float]
    control: str = ''


@dataclass(frozen=True)
class Plan:
    analysis: Analysis
    joints: tuple[Joint, ...]
    bindings: tuple[tuple[str, str], ...]
    minimum_bones: int
    front_position: tuple[float, float, float]

    @property
    def wheel_counts(self):
        """Physical wheel joints by axle; useful when reviewing Simple-mode options."""
        counts = {'front': 0, 'rear': 0, 'other': 0}
        for joint in self.joints:
            if joint.control != 'wheel':
                continue
            label = joint.name.removeprefix('Wheel.')
            key = ('front' if label.startswith(('F', 'Front')) else
                   'rear' if label.startswith(('R', 'Rear')) else 'other')
            counts[key] += 1
        return counts


def _axis(options):
    forward = (options.forward_sign, 0, 0) if options.forward_axis == 'X' else (
        0, options.forward_sign, 0)
    left = (-forward[1], forward[0], 0)
    return forward, left


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _distance(a, b):
    return sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _add(a, b, scale=1.0):
    return tuple(x + scale * y for x, y in zip(a, b))


def analyze(parts, options=Options()):
    """Classify distinct meshes, retaining editable per-mesh overrides."""
    parts = tuple(parts)
    if not parts or len({p.node for p in parts}) != len(parts):
        raise ValueError('Select distinct vehicle mesh transforms')
    lo = tuple(min(p.minimum[i] for p in parts) for i in range(3))
    hi = tuple(max(p.maximum[i] for p in parts) for i in range(3))
    center = tuple((a + b) * .5 for a, b in zip(lo, hi))
    total = tuple(b - a for a, b in zip(lo, hi))
    forward, left = _axis(options)
    lateral = 1 if options.forward_axis == 'X' else 0
    longitudinal = 0 if options.forward_axis == 'X' else 1
    result = []
    for part in parts:
        if part.kind != 'AUTO':
            result.append(part)
            continue
        short = part.node.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
        rules = (AIRCRAFT_NAMES if options.vehicle == 'AIRPLANE' else ()) + COMMON_NAMES
        kind = next((label for label, pattern in rules if re.search(pattern, short, re.I)), None)
        if not kind:
            size = part.size
            radius = (size[longitudinal] + size[2]) * .25
            roundish = abs(size[longitudinal] - size[2]) / max(
                size[longitudinal], size[2], 1e-9) < .42
            thin = size[lateral] < .85 * max(size[longitudinal], size[2])
            low = part.center[2] < lo[2] + total[2] * .72
            scale = total[longitudinal] * .045 <= radius <= total[longitudinal] * .34
            side = abs(_dot(_add(part.center, center, -1), left)) > total[lateral] * .17
            if options.vehicle in {'MOTORCYCLE', 'BICYCLE'}:
                side = abs(_dot(_add(part.center, center, -1), left)) < total[lateral] * .35
            if options.vehicle == 'AIRPLANE':
                side = True
            kind = 'WHEEL' if roundish and thin and low and scale and side and (
                max(size) < .45 * max(total)) else 'BODY'
        result.append(replace(part, kind=kind))
    return Analysis(options, tuple(result), lo, hi)


def _wheel_labels(analysis):
    """Group concentric meshes, then label wheels by axle and side."""
    parts, options = analysis.parts, analysis.options
    forward, left = _axis(options)
    center = tuple((a + b) * .5 for a, b in zip(analysis.minimum, analysis.maximum))
    span = _distance(analysis.minimum, analysis.maximum)
    wheels = sorted(((i, p) for i, p in enumerate(parts) if p.kind == 'WHEEL'),
                    key=lambda item: (-_dot(_add(item[1].center, center, -1), forward),
                                      item[1].node))
    physical = []
    for i, part in wheels:
        radius = max(part.size) * .5
        match = next((g for g in physical if _distance(g[0], part.center) <
                      max(.15 * radius, .02 * span)), None)
        if match is None:
            physical.append((part.center, [i]))
        else:
            match[1].append(i)

    def override(indices):
        overrides = {parts[i].axle for i in indices} - {'AUTO'}
        if len(overrides) > 1:
            raise ValueError('Conflicting front/rear overrides on the same wheel')
        return next(iter(overrides), None)

    # Optional Simple-mode counts divide detected physical wheels by
    # longitudinal position. Explicit per-mesh axle overrides take priority.
    requested = None
    if options.front_wheels is not None or options.rear_wheels is not None:
        total = len(physical)
        front_count = (options.front_wheels if options.front_wheels is not None
                       else total - options.rear_wheels)
        rear_count = (options.rear_wheels if options.rear_wheels is not None
                      else total - front_count)
        if front_count < 0 or rear_count < 0 or front_count + rear_count != total:
            raise ValueError('Simple wheel counts must total %d detected physical wheels; '
                             'separate or reclassify meshes and analyze again' % total)
        forced = [override(ids) for _, ids in physical]
        chosen = {n for n, axle in enumerate(forced) if axle == 'FRONT'}
        if len(chosen) > front_count or forced.count('REAR') > rear_count:
            raise ValueError('Simple wheel counts conflict with per-mesh front/rear overrides')
        for n, axle in enumerate(forced):
            if axle == 'AUTO' or axle is None:
                if len(chosen) < front_count:
                    chosen.add(n)
        if len(chosen) != front_count:
            raise ValueError('Simple wheel counts conflict with per-mesh front/rear overrides')
        requested = ['FRONT' if n in chosen else 'REAR' for n in range(total)]

    if options.vehicle in {'MOTORCYCLE', 'BICYCLE'}:
        if requested is not None:
            used = {'Front': 0, 'Rear': 0}
            result = {}
            for n, (_, ids) in enumerate(physical):
                prefix = 'Front' if requested[n] == 'FRONT' else 'Rear'
                used[prefix] += 1
                name = prefix + (str(used[prefix]) if used[prefix] > 1 else '')
                result.update((i, name) for i in ids)
            return result
        return {i: ('Front' if override(ids) == 'FRONT' else
                    'Rear' if override(ids) == 'REAR' else
                    'Front' if n == 0 else 'Rear' if n == len(physical)-1
                    else 'Mid%02d' % n)
                for n, (_, ids) in enumerate(physical) for i in ids}

    if requested is not None:
        labels, used = {}, {}
        for n, (position, indices) in enumerate(physical):
            prefix = 'F' if requested[n] == 'FRONT' else 'R'
            side = 'L' if _dot(_add(position, center, -1), left) >= 0 else 'R'
            stem = prefix + side
            used[stem] = used.get(stem, 0) + 1
            label = stem + (str(used[stem]) if used[stem] > 1 else '')
            labels.update((i, label) for i in indices)
        return labels

    axles = []
    tolerance = max(.04 * span, .10 * (analysis.maximum[2] - analysis.minimum[2]))
    for n, (position, _) in enumerate(physical):
        projection = _dot(_add(position, center, -1), forward)
        group = next((a for a in axles if abs(a[0] - projection) < tolerance), None)
        if group is None:
            group = [projection, []]
            axles.append(group)
        group[1].append(n)
    labels, used = {}, {}
    for n, (_, members) in enumerate(axles):
        overrides = {override(physical[gi][1]) for gi in members} - {None}
        if len(overrides) > 1:
            raise ValueError('Conflicting front/rear overrides on one axle')
        choice = next(iter(overrides), None)
        prefix = ('F' if choice == 'FRONT' else 'R' if choice == 'REAR' else
                  'F' if n == 0 else 'R' if n == len(axles)-1 else 'M%d' % n)
        used[prefix] = used.get(prefix, 0) + 1
        if used[prefix] > 1:
            prefix += str(used[prefix])
        sides = {}
        for gi in members:
            side = 'L' if _dot(_add(physical[gi][0], center, -1), left) >= 0 else 'R'
            sides[side] = sides.get(side, 0) + 1
            label = prefix + side + (str(sides[side]) if sides[side] > 1 else '')
            for i in physical[gi][1]:
                labels[i] = label
    return labels


def _steering(analysis, labels):
    parts, options = analysis.parts, analysis.options
    members = {}
    for index, label in labels.items():
        members.setdefault(label, []).append(parts[index])
    if options.vehicle != 'AIRPLANE':
        return {name for name in members if name.startswith(('F', 'Front'))}
    front = {name for name in members if name.startswith(('F', 'Front'))}
    rear = {name for name in members if name.startswith(('R', 'Rear'))}
    result = set()
    for name, group in members.items():
        choices = {p.steer for p in group} - {'AUTO'}
        if len(choices) > 1:
            raise ValueError('Conflicting steering overrides on the same wheel')
        if 'YES' in choices or not choices and (
                any(re.search(r'nose|tail[_ .-]?wheel', p.node, re.I) for p in group) or
                name in front and len(front) == 1 and len(rear) > 1 or
                name in rear and len(rear) == 1 and len(front) > 1):
            result.add(name)
    return result


def plan_rig(analysis):
    """Create all joint positions and assignments before touching Maya."""
    parts, options = analysis.parts, analysis.options
    forward, left = _axis(options)
    lo, hi = analysis.minimum, analysis.maximum
    center = tuple((a + b) * .5 for a, b in zip(lo, hi))
    reach = max(.07 * (hi[2] - lo[2]), .02)
    joints = [Joint('Root', None, (center[0], center[1], lo[2])),
              Joint('Body', 'Root', center)]
    bind = []
    labels = _wheel_labels(analysis)
    steer = _steering(analysis, labels)
    wheel_groups = {}
    for i, name in labels.items():
        wheel_groups.setdefault(name, []).append(i)
    gears = {}
    if options.vehicle == 'AIRPLANE' and options.mode == 'ADVANCED':
        for i, part in enumerate(parts):
            if part.kind == 'GEAR':
                name = 'Gear.%03d' % (i+1)
                gears[i] = name
                joints.append(Joint(name, 'Body', (part.center[0], part.center[1], part.maximum[2]),
                                    'retract'))
    wheel_joint = {}
    spring_joint = {}
    for name, indices in sorted(wheel_groups.items()):
        part = parts[indices[0]]
        parent = 'Root'
        if gears:
            radius = _distance(part.minimum, part.maximum) * .5
            candidates = [( _distance(parts[gi].center[:2], part.center[:2]), gear_name)
                          for gi, gear_name in gears.items()
                          if all(parts[gi].minimum[axis] - max(.25, radius*.8) <=
                                 part.center[axis] <= parts[gi].maximum[axis] +
                                 max(.25, radius*.8) for axis in (0, 1))]
            if candidates:
                parent = min(candidates)[1]
        if options.mode == 'ADVANCED':
            spring_joint[name] = 'Suspension.' + name + '.01'
            joints.append(Joint(spring_joint[name], parent, part.center, 'suspension'))
            parent = spring_joint[name]
        if name in steer:
            control = 'Steer.' + name
            joints.append(Joint(control, parent, part.center, 'steering'))
            parent = control
        wheel_joint[name] = 'Wheel.' + name
        joints.append(Joint(wheel_joint[name], parent, part.center, 'wheel'))
    for i, part in enumerate(parts):
        kind, parent = part.kind, 'Body'
        if kind == 'IGNORE':
            continue
        if kind == 'WHEEL':
            name = wheel_joint[labels[i]]
        elif kind == 'GEAR' and i in gears:
            name = gears[i]
        elif kind == 'PROPELLER' and options.vehicle == 'AIRPLANE':
            name = 'Propeller.%03d' % (i+1)
            joints.append(Joint(name, parent, part.center, 'propeller'))
        elif (kind in SURFACES and options.vehicle == 'AIRPLANE' or
              kind in {'DOOR', 'HOOD', 'TRUNK'}) and options.mode == 'ADVANCED':
            name = kind.title() + '.%03d' % (i+1)
            longitudinal = abs(_dot(part.size, forward)) * .45
            pivot = _add(part.center, forward, -longitudinal if kind == 'HOOD' else longitudinal)
            joints.append(Joint(name, parent, pivot, kind.lower()))
        else:
            name = 'Body'
        bind.append((part.node, name))
    required = len(joints)
    if options.mode == 'ADVANCED' and wheel_groups:
        extra = max(0, options.bone_count - required)
        for n in range(extra):
            name = sorted(wheel_groups)[n % len(wheel_groups)]
            spring = spring_joint[name]
            new = 'Suspension.' + name + '.%02d' % (2 + n // len(wheel_groups))
            parent = next(j.parent for j in joints if j.name == spring)
            joints = [replace(j, parent=new) if j.name == spring else j for j in joints]
            joints.append(Joint(new, parent, parts[wheel_groups[name][0]].center, 'suspension'))
    front = _add(center, forward, (hi[0] - lo[0] if options.forward_axis == 'X'
                                   else hi[1] - lo[1]) * .5)
    front = (front[0], front[1], hi[2] + max(.05, .05 * _distance(lo, hi)))
    result = Plan(analysis, tuple(joints), tuple(bind), required, front)
    if len({j.name for j in result.joints}) != len(result.joints):
        raise ValueError('Duplicate joints; check wheel overrides and part names')
    return result
