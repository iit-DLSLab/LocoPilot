"""URDF parsing helpers for joint compatibility checks."""

from dataclasses import dataclass
from typing import Optional
from xml.etree import ElementTree


MOVABLE_JOINT_TYPES = frozenset({'revolute', 'continuous', 'prismatic'})


@dataclass(frozen=True)
class JointInfo:
    """Name, type, and position limits of a URDF joint."""

    name: str
    joint_type: str
    lower_limit: Optional[float] = None
    upper_limit: Optional[float] = None


def parse_joints(urdf_xml: str) -> dict[str, JointInfo]:
    """Extract joint information from a URDF string, keyed by name."""
    root = ElementTree.fromstring(urdf_xml)
    if root.tag != 'robot':
        raise ValueError(
            f"Robot description root tag is '{root.tag}', expected 'robot'"
        )
    joints = {}
    for joint in root.findall('joint'):
        name = joint.get('name')
        joint_type = joint.get('type')
        if name is None or joint_type is None:
            continue
        limit = joint.find('limit')
        joints[name] = JointInfo(
            name=name,
            joint_type=joint_type,
            lower_limit=_limit_attribute(limit, 'lower'),
            upper_limit=_limit_attribute(limit, 'upper'),
        )
    return joints


def check_coupled_joints(
    leader_urdf: str,
    follower_urdf: str,
    coupled_joint_names,
) -> tuple[list[str], list[str]]:
    """
    Check that both descriptions expose matching coupled joints.

    Returns a tuple (errors, warnings). Errors make the coupling
    unusable (missing or non-movable joints, unparsable descriptions);
    warnings flag joint limit mismatches between the two arms.
    """
    errors: list[str] = []
    warnings: list[str] = []
    joints_by_side = {}
    for side, urdf_xml in (
        ('leader', leader_urdf),
        ('follower', follower_urdf),
    ):
        try:
            joints_by_side[side] = parse_joints(urdf_xml)
        except (ElementTree.ParseError, ValueError) as exc:
            errors.append(f'Invalid {side} robot description: {exc}')
    if errors:
        return errors, warnings

    for joint_name in coupled_joint_names:
        infos = {}
        for side, joints in joints_by_side.items():
            info = joints.get(joint_name)
            if info is None:
                errors.append(
                    f"Joint '{joint_name}' is missing from the "
                    f'{side} robot description'
                )
            elif info.joint_type not in MOVABLE_JOINT_TYPES:
                errors.append(
                    f"Joint '{joint_name}' has non-movable type "
                    f"'{info.joint_type}' in the {side} robot description"
                )
            else:
                infos[side] = info
        if len(infos) != 2:
            continue
        leader_info = infos['leader']
        follower_info = infos['follower']
        if leader_info.joint_type != follower_info.joint_type:
            errors.append(
                f"Joint '{joint_name}' type differs: leader is "
                f"'{leader_info.joint_type}', follower is "
                f"'{follower_info.joint_type}'"
            )
        elif (
            leader_info.lower_limit != follower_info.lower_limit
            or leader_info.upper_limit != follower_info.upper_limit
        ):
            warnings.append(
                f"Joint '{joint_name}' limits differ: leader is "
                f'[{leader_info.lower_limit}, {leader_info.upper_limit}], '
                f'follower is [{follower_info.lower_limit}, '
                f'{follower_info.upper_limit}]'
            )
    return errors, warnings


def _limit_attribute(limit, attribute: str) -> Optional[float]:
    if limit is None:
        return None
    value = limit.get(attribute)
    if value is None:
        return None
    return float(value)
