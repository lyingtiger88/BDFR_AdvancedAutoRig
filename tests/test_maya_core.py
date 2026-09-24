"""Exercise the Maya-independent planner without an Autodesk installation."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maya_autorig import Options, Part, analyze, plan_rig


def part(name, pos, size, kind='AUTO', **kw):
    low = tuple(c - d*.5 for c, d in zip(pos, size))
    high = tuple(c + d*.5 for c, d in zip(pos, size))
    return Part('|Vehicle|' + name, low, high, 8, kind=kind, **kw)


def car():
    return [part('Body', (0, 0, 1), (1.8, 3.2, .7))] + [
        part('Wheel_%s_%s' % (x, y), (x*.9, y*1.1, .42), (.22, .82, .82))
        for x in (-1, 1) for y in (-1, 1)]


def airplane():
    return [part('Fuselage', (0, 0, 1.4), (1.1, 5, .7)),
            part('Wing_L', (-2, 0, 1.5), (3, 1, .12)),
            part('NoseWheel', (0, 1.8, .35), (.18, .55, .55)),
            part('MainWheel_L', (-.8, -.9, .35), (.18, .55, .55)),
            part('MainWheel_R', (.8, -.9, .35), (.18, .55, .55)),
            part('NoseGear', (0, 1.8, .72), (.12, .16, .65)),
            part('MainGear_L', (-.8, -.9, .72), (.12, .16, .65)),
            part('MainGear_R', (.8, -.9, .72), (.12, .16, .65)),
            part('Propeller_1', (0, 2.65, 1.4), (1.4, .12, .16)),
            part('Aileron_L', (-3, -.45, 1.5), (.75, .3, .08)),
            part('Aileron_R', (3, -.45, 1.5), (.75, .3, .08)),
            part('Elevator', (0, -2.4, 1.5), (.9, .35, .08)),
            part('Rudder', (0, -2.35, 1.85), (.09, .35, .7)),
            part('Flap_L', (-1.45, -.5, 1.5), (.55, .3, .08))]


class PlannerTests(unittest.TestCase):
    def test_car_simple(self):
        plan = plan_rig(analyze(car()))
        self.assertEqual(len(plan.joints), 8)
        self.assertEqual(len(plan.bindings), 5)
        self.assertEqual(sum(j.name.startswith('Steer.') for j in plan.joints), 2)
        self.assertEqual(plan.front_position[1], 1.51 + .09)  # front edge of wheels
        self.assertIn('Body', dict(plan.bindings).values())

    def test_car_advanced_chain_and_budget(self):
        opts = Options(mode='ADVANCED', bone_count=19)
        plan = plan_rig(analyze(car(), opts))
        self.assertEqual(len(plan.joints), 19)
        self.assertEqual(plan.minimum_bones, 12)
        joints = {j.name: j for j in plan.joints}
        for joint in joints.values():
            if joint.parent:
                self.assertIn(joint.parent, joints)
        # The first spring is beneath every extra segment and still drives the wheel.
        wheel = joints['Wheel.FL']
        while wheel.parent != 'Root':
            wheel = joints[wheel.parent]
        self.assertTrue(wheel.name.startswith('Suspension.'))

    def test_plane_simple_and_advanced(self):
        simple = plan_rig(analyze(airplane(), Options(vehicle='AIRPLANE')))
        self.assertEqual(len(simple.joints), 7)
        self.assertEqual(sum(j.name.startswith('Steer.') for j in simple.joints), 1)
        self.assertEqual(sum(j.name.startswith('Propeller.') for j in simple.joints), 1)
        self.assertEqual(dict(simple.bindings)['|Vehicle|NoseGear'], 'Body')
        full = plan_rig(analyze(airplane(), Options(vehicle='AIRPLANE', mode='ADVANCED',
                                                     bone_count=23)))
        self.assertEqual(len(full.joints), 23)
        bindings = dict(full.bindings)
        self.assertTrue(bindings['|Vehicle|Aileron_L'].startswith('Aileron.'))
        self.assertTrue(bindings['|Vehicle|NoseGear'].startswith('Gear.'))
        joints = {j.name: j for j in full.joints}
        nose = joints[bindings['|Vehicle|NoseWheel']]
        ancestors = set()
        while nose.parent:
            ancestors.add(nose.parent)
            nose = joints[nose.parent]
        self.assertIn(bindings['|Vehicle|NoseGear'], ancestors)

    def test_explicit_overrides_and_y_up(self):
        opts = Options(vehicle='AIRPLANE', up_axis='Y', forward_axis='Z', forward_sign=-1)
        objects = airplane()
        objects[2] = part('NoseWheel', (0, 1.8, .35), (.18, .55, .55), steer='NO')
        plan = plan_rig(analyze(objects, opts))
        self.assertEqual(sum(j.name.startswith('Steer.') for j in plan.joints), 0)
        self.assertLess(plan.front_position[1], 0)
        with self.assertRaises(ValueError):
            Options(up_axis='Y', forward_axis='Y')

    def test_validation(self):
        with self.assertRaises(ValueError):
            analyze([])
        with self.assertRaises(ValueError):
            analyze(car() + car())
        with self.assertRaises(ValueError):
            Part('|Bad', (0, 0, 0), (0, 0, 0), 1)
        # A flat panel is valid; Maya often stores control surfaces this way.
        self.assertEqual(part('Panel', (0, 0, 0), (1, 1, 0)).size[2], 0)


if __name__ == '__main__':
    unittest.main()
