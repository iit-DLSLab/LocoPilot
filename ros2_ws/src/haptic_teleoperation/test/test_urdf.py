"""Unit tests for URDF joint compatibility checks."""

from haptic_teleoperation.utils.urdf import (
    check_coupled_joints,
    parse_joints,
)


def _make_urdf(joints: str) -> str:
    return f'<robot name="arm">{joints}</robot>'


REVOLUTE_JOINT = (
    '<joint name="{name}" type="revolute">'
    '<limit lower="{lower}" upper="{upper}"/>'
    '</joint>'
)


def _revolute(name: str, lower: float = -3.0, upper: float = 3.0) -> str:
    return REVOLUTE_JOINT.format(name=name, lower=lower, upper=upper)


def test_parse_joints_extracts_types_and_limits():
    urdf = _make_urdf(
        _revolute('joint1', -1.5, 1.5)
        + '<joint name="flange" type="fixed"/>'
    )
    joints = parse_joints(urdf)
    assert joints['joint1'].joint_type == 'revolute'
    assert joints['joint1'].lower_limit == -1.5
    assert joints['joint1'].upper_limit == 1.5
    assert joints['flange'].joint_type == 'fixed'


def test_matching_descriptions_pass():
    urdf = _make_urdf(_revolute('joint1') + _revolute('joint2'))
    errors, warnings = check_coupled_joints(
        urdf, urdf, ['joint1', 'joint2'],
    )
    assert errors == []
    assert warnings == []


def test_missing_joint_is_an_error():
    leader = _make_urdf(_revolute('joint1') + _revolute('joint2'))
    follower = _make_urdf(_revolute('joint1'))
    errors, _ = check_coupled_joints(leader, follower, ['joint1', 'joint2'])
    assert len(errors) == 1
    assert 'joint2' in errors[0]
    assert 'follower' in errors[0]


def test_fixed_joint_is_an_error():
    leader = _make_urdf(_revolute('joint1'))
    follower = _make_urdf('<joint name="joint1" type="fixed"/>')
    errors, _ = check_coupled_joints(leader, follower, ['joint1'])
    assert len(errors) == 1
    assert 'non-movable' in errors[0]


def test_limit_mismatch_is_a_warning():
    leader = _make_urdf(_revolute('joint1', -3.0, 3.0))
    follower = _make_urdf(_revolute('joint1', -2.0, 3.0))
    errors, warnings = check_coupled_joints(leader, follower, ['joint1'])
    assert errors == []
    assert len(warnings) == 1
    assert 'limits differ' in warnings[0]


def test_invalid_description_is_an_error():
    follower = _make_urdf(_revolute('joint1'))
    errors, _ = check_coupled_joints('not a urdf', follower, ['joint1'])
    assert len(errors) == 1
    assert 'Invalid leader robot description' in errors[0]
