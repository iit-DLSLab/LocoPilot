"""Tests for joystick button to joint reference mapping."""

from types import SimpleNamespace

from haptic_teleoperation.nodes.joy_joint_controller import (
    _mappings_from_parameters,
    ButtonMapping,
    JoyJointMapper,
)


def test_hold_mode_tracks_button_state():
    """Hold mappings remain high exactly while their button is held."""
    mapper = JoyJointMapper([
        ButtonMapping(1, 'gripper', 'hold', -1.0, 2.0),
    ])

    assert mapper.update([0, 0]) == [-1.0]
    assert mapper.update([0, 1]) == [2.0]
    assert mapper.update([0, 1]) == [2.0]
    assert mapper.update([0, 0]) == [-1.0]


def test_trigger_mode_toggles_only_on_rising_edges():
    """Trigger mappings toggle once per press, not for every Joy message."""
    mapper = JoyJointMapper([
        ButtonMapping(0, 'tool', 'trigger', 0.1, 0.9),
    ])

    assert mapper.update([0]) == [0.1]
    assert mapper.update([1]) == [0.9]
    assert mapper.update([1]) == [0.9]
    assert mapper.update([0]) == [0.9]
    assert mapper.update([1]) == [0.1]


def test_missing_button_is_treated_as_released():
    """Short Joy button arrays safely put hold mappings in LOW."""
    mapper = JoyJointMapper([
        ButtonMapping(3, 'tool', 'hold', 0.0, 1.0),
    ])

    assert mapper.update([0, 0]) == [0.0]


def test_mapped_parameters_follow_configured_joint_order():
    """The joints list determines JointState order for __map entries."""
    entries = {
        'joint_a': SimpleNamespace(
            button_index=2,
            mode='trigger',
            low_value=-1.0,
            high_value=1.0,
        ),
        'joint_b': SimpleNamespace(
            button_index=0,
            mode='hold',
            low_value=0.0,
            high_value=0.5,
        ),
    }
    params = SimpleNamespace(
        joints=['joint_b', 'joint_a'],
        mappings=SimpleNamespace(get_entry=entries.__getitem__),
    )

    mappings = _mappings_from_parameters(params)

    assert [mapping.joint_name for mapping in mappings] == [
        'joint_b',
        'joint_a',
    ]
    assert [mapping.button_index for mapping in mappings] == [0, 2]
