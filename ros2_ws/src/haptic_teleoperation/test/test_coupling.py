"""Unit tests for the joint-space spring-damper coupling law."""

from haptic_teleoperation.utils.coupling import coupling_efforts
import numpy as np


STIFFNESS = np.array([50.0, 30.0])
DAMPING = np.array([2.0, 1.0])


def test_zero_effort_when_states_match():
    positions = np.array([0.1, -0.4])
    velocities = np.array([0.2, 0.0])
    efforts = coupling_efforts(
        positions, velocities, positions, velocities, STIFFNESS, DAMPING,
    )
    assert np.allclose(efforts, 0.0)


def test_spring_damper_law():
    efforts = coupling_efforts(
        np.array([0.0, 0.0]),
        np.array([0.0, 0.0]),
        np.array([0.1, -0.2]),
        np.array([0.5, 0.0]),
        STIFFNESS,
        DAMPING,
    )
    assert np.allclose(efforts, [50.0 * 0.1 + 2.0 * 0.5, 30.0 * -0.2])


def test_coupling_efforts_are_symmetric():
    leader_positions = np.array([0.3, -0.1])
    leader_velocities = np.array([0.1, 0.4])
    follower_positions = np.array([0.25, 0.05])
    follower_velocities = np.array([-0.1, 0.2])
    leader_efforts = coupling_efforts(
        leader_positions,
        leader_velocities,
        follower_positions,
        follower_velocities,
        STIFFNESS,
        DAMPING,
    )
    follower_efforts = coupling_efforts(
        follower_positions,
        follower_velocities,
        leader_positions,
        leader_velocities,
        STIFFNESS,
        DAMPING,
    )
    assert np.allclose(leader_efforts, -follower_efforts)
