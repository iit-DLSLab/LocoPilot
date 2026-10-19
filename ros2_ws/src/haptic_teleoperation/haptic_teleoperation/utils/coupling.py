"""Joint-space spring-damper coupling law for P-P teleoperation."""

import numpy as np


def coupling_efforts(
    positions,
    velocities,
    other_positions,
    other_velocities,
    stiffness,
    damping,
) -> np.ndarray:
    """
    Compute per-joint efforts pulling one arm toward the other.

    Implements one side of the position-position (P-P) bilateral
    architecture: a virtual spring-damper between each pair of joints,
    tau = K (q_other - q_self) + D (dq_other - dq_self).
    """
    position_error = np.asarray(other_positions) - np.asarray(positions)
    velocity_error = np.asarray(other_velocities) - np.asarray(velocities)
    return (
        np.asarray(stiffness) * position_error
        + np.asarray(damping) * velocity_error
    )


def force_reflection_efforts(gain, other_external_torque) -> np.ndarray:
    """
    Compute per-joint efforts reflecting the other arm's estimated contact torque.

    Implements the force channel of the P-P + force-reflection bilateral
    architecture: tau = gain * tau_ext_other, where tau_ext_other is the
    other arm's external torque estimate, received over ROS rather than
    derived from position error.
    """
    return np.asarray(gain) * np.asarray(other_external_torque)
