"""Unit tests for the force-reflection effort law."""

from haptic_teleoperation.utils.coupling import force_reflection_efforts
import numpy as np


GAIN = np.array([1.0, 0.5])


def test_zero_effort_when_no_external_torque():
    efforts = force_reflection_efforts(GAIN, np.array([0.0, 0.0]))
    assert np.allclose(efforts, 0.0)


def test_scales_other_external_torque_by_gain():
    efforts = force_reflection_efforts(GAIN, np.array([2.0, -4.0]))
    assert np.allclose(efforts, [1.0 * 2.0, 0.5 * -4.0])


def test_negative_gain_flips_sign():
    efforts = force_reflection_efforts(np.array([-1.0, -1.0]), np.array([3.0, -3.0]))
    assert np.allclose(efforts, [-3.0, 3.0])
