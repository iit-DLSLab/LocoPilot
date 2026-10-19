#!/usr/bin/env python3
"""Export teleoperation bags to a LeRobot dataset.

Each bag is split into episodes using the episode-marker buttons of the
handle controller (start, end; a second start before an end restarts the
episode). Every episode is resampled at a fixed rate on the bag receive
clock, holding the latest message of each stream, and written with the
LeRobot dataset API.

Per frame:
    action                          [vx, vy, wz, pitch, joint1..joint6, gripper]
                                    the unified loco-manipulation command
    observation.state               follower joints and gripper, base linear
                                    and angular velocity, base orientation
    observation.images.<camera>     gripper/world colour and depth

The base command is read from a command topic when the bag has one; otherwise
it is reconstructed from the joystick messages with the same filter the
locomotion controller applies. Topics and mappings can be overridden with a
YAML file (--config); see DEFAULT_CONFIG.

Example:
    python scripts/export_lerobot.py go2piper_pickplace_* \\
        --repo-id local/go2piper_pickplace --root datasets/go2piper_pickplace \\
        --task "Pick the red cube and place it on the blue base"

Requires: lerobot>=0.6, rosbags, opencv-python, pyyaml.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass, field
from pathlib import Path
import shutil
import sys

import cv2
import numpy as np
import yaml

try:
    from rosbags.highlevel import AnyReader
except ImportError as exc:  # pragma: no cover - import guard for users.
    raise SystemExit('This script requires rosbags: python -m pip install rosbags') from exc


ARM_JOINTS = ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6']

DEFAULT_CONFIG = {
    'robot_type': 'go2_piper_l',
    'markers': {'topic': '/joycon', 'start_button': 3, 'end_button': 2},
    'arm_command': {
        'topic': '/follower/control/move_mit_joint_states',
        'joints': ARM_JOINTS,
    },
    'arm_state': {
        'topic': '/follower/feedback/joint_states',
        'joints': ARM_JOINTS,
        'gripper_joint': 'gripper',
    },
    'odometry': {'topic': '/muse/proprioceptive_sensor_fusion'},
    # Gripper reference, as produced by haptic_teleoperation's
    # joy_joint_controller (config/joy_joint_controller_params.yaml).
    'gripper_command': {
        'topic': None,  # sensor_msgs/JointState with a 'gripper' joint
        'joy_topic': '/joycon',
        'button': 8,
        'mode': 'hold',  # hold | trigger
        'low_value': 0.1,
        'high_value': 0.0,
    },
    # Base reference. Replays the joystick filter of the locomotion controller
    # (locomanipulation-teleop-isaaclab/deploy/joystick.py) unless 'topic'
    # names a recorded geometry_msgs/Twist or TwistStamped command.
    'base_command': {
        'topic': None,
        'joy_topic': '/joy',
        'vx_axis': 1,
        'vy_axis': 0,
        'wz_axis': 3,
        'vx_scale': 1.0 / 3.5,
        'vy_scale': 1.0 / 3.5,
        'wz_scale': 1.0 / 2.0,
        'filter': 0.7,
        'min_axes': 5,
        'timeout_s': 1.0,
        'arm_mode_button': 0,  # toggles arm-joystick mode, freezing the base
        'debounce_s': 1.0,
        # Body pitch: from a std_msgs/Float32/Float64 topic, from a joystick
        # axis ('absolute' maps the axis, 'rate' integrates it), or constant.
        'pitch_topic': None,
        'pitch_axis': None,
        'pitch_mode': 'rate',
        'pitch_scale': 0.5,
        'pitch_min': -0.5,
        'pitch_max': 0.5,
        'pitch_default': 0.0,
    },
    # Candidate topics per camera stream; the first one present is used.
    'cameras': {
        'gripper_rgb': [
            '/gripper_camera/realsense_camera_node/color/image_raw/compressed',
            '/gripper_camera/realsense_camera_node/color/image_raw',
        ],
        'gripper_depth': [
            '/gripper_camera/realsense_camera_node/aligned_depth_to_color/image_raw/compressedDepth',
            '/gripper_camera/realsense_camera_node/depth/image_rect_raw/compressedDepth',
            '/gripper_camera/realsense_camera_node/depth/image_rect_raw',
        ],
        'world_rgb': [
            '/world_camera/realsense_camera_node/color/image_raw/compressed',
            '/world_camera/realsense_camera_node/color/image_raw',
        ],
        'world_depth': [
            '/world_camera/realsense_camera_node/aligned_depth_to_color/image_raw/compressedDepth',
            '/world_camera/realsense_camera_node/depth/image_rect_raw/compressedDepth',
            '/world_camera/realsense_camera_node/depth/image_rect_raw',
        ],
    },
}

ACTION_NAMES = ['base_vx', 'base_vy', 'base_wz', 'base_pitch', *ARM_JOINTS, 'gripper']
STATE_NAMES = [
    *ARM_JOINTS, 'gripper',
    'base_lin_vel_x', 'base_lin_vel_y', 'base_lin_vel_z',
    'base_ang_vel_x', 'base_ang_vel_y', 'base_ang_vel_z',
    'base_quat_x', 'base_quat_y', 'base_quat_z', 'base_quat_w',
]


@dataclass
class Signal:
    """Zero-order-hold time series on the bag receive clock."""

    times: np.ndarray
    values: np.ndarray

    @classmethod
    def from_lists(cls, times, values, width):
        if not times:
            return cls(np.empty(0, dtype=np.int64), np.empty((0, width)))
        return cls(np.asarray(times, dtype=np.int64), np.asarray(values, dtype=np.float64))

    def first_time(self):
        return int(self.times[0]) if len(self.times) else None

    def at(self, t):
        index = np.searchsorted(self.times, t, side='right') - 1
        return None if index < 0 else self.values[index]


@dataclass
class Episode:
    start: int
    end: int
    times: list = field(default_factory=list)


def deep_update(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_update(base[key], value)
        else:
            base[key] = value
    return base


def ordered_values(msg, names, attribute='position'):
    values = list(getattr(msg, attribute))
    index = {name: i for i, name in enumerate(msg.name)}
    if all(name in index for name in names):
        return [values[index[name]] for name in names]
    if len(values) >= len(names):
        return values[:len(names)]
    return None


def rising_edge(buttons, previous, index):
    return (
        index is not None
        and index < len(buttons)
        and buttons[index] == 1
        and (previous is None or index >= len(previous) or previous[index] == 0)
    )


def joy_messages(reader, topic):
    connections = [c for c in reader.connections if c.topic == topic]
    for connection, t, raw in reader.messages(connections=connections):
        msg = reader.deserialize(raw, connection.msgtype)
        yield t, np.asarray(msg.buttons), np.asarray(msg.axes, dtype=np.float64)


def find_episodes(reader, cfg):
    markers = cfg['markers']
    episodes, start, previous = [], None, None
    for t, buttons, _ in joy_messages(reader, markers['topic']):
        if rising_edge(buttons, previous, markers['start_button']):
            start = t
        elif rising_edge(buttons, previous, markers['end_button']) and start is not None:
            episodes.append(Episode(start, t))
            start = None
        previous = buttons
    return episodes, start is not None


def read_joint_signal(reader, topic, names):
    times, values = [], []
    for connection in [c for c in reader.connections if c.topic == topic]:
        for _, t, raw in reader.messages(connections=[connection]):
            msg = reader.deserialize(raw, connection.msgtype)
            row = ordered_values(msg, names)
            if row is not None:
                times.append(t)
                values.append(row)
    order = np.argsort(times, kind='stable')
    return Signal.from_lists([times[i] for i in order], [values[i] for i in order], len(names))


def read_odometry(reader, topic):
    times, values = [], []
    connections = [c for c in reader.connections if c.topic == topic]
    for connection, t, raw in reader.messages(connections=connections):
        msg = reader.deserialize(raw, connection.msgtype)
        lin, ang, quat = msg.twist.twist.linear, msg.twist.twist.angular, msg.pose.pose.orientation
        times.append(t)
        values.append([lin.x, lin.y, lin.z, ang.x, ang.y, ang.z, quat.x, quat.y, quat.z, quat.w])
    return Signal.from_lists(times, values, 10)


def read_gripper_command(reader, cfg):
    times, values = [], []
    if cfg['topic']:
        signal = read_joint_signal(reader, cfg['topic'], ['gripper'])
        if len(signal.times):
            return signal
    value, previous = cfg['low_value'], None
    for t, buttons, _ in joy_messages(reader, cfg['joy_topic']):
        index = cfg['button']
        pressed = index < len(buttons) and buttons[index] == 1
        if cfg['mode'] == 'hold':
            value = cfg['high_value'] if pressed else cfg['low_value']
        elif rising_edge(buttons, previous, index):
            value = cfg['low_value'] if value == cfg['high_value'] else cfg['high_value']
        times.append(t)
        values.append([value])
        previous = buttons
    return Signal.from_lists(times, values, 1)


def read_scalar(reader, topic):
    times, values = [], []
    connections = [c for c in reader.connections if c.topic == topic]
    for connection, t, raw in reader.messages(connections=connections):
        times.append(t)
        values.append([float(reader.deserialize(raw, connection.msgtype).data)])
    return Signal.from_lists(times, values, 1)


def read_base_command(reader, cfg):
    """Return a Signal of [vx, vy, wz, pitch] and a short description of its source."""
    topics = {c.topic for c in reader.connections}
    pitch = None
    if cfg['pitch_topic'] and cfg['pitch_topic'] in topics:
        pitch = read_scalar(reader, cfg['pitch_topic'])

    if cfg['topic'] and cfg['topic'] in topics:
        times, values = [], []
        connections = [c for c in reader.connections if c.topic == cfg['topic']]
        for connection, t, raw in reader.messages(connections=connections):
            msg = reader.deserialize(raw, connection.msgtype)
            twist = getattr(msg, 'twist', msg)
            times.append(t)
            values.append([twist.linear.x, twist.linear.y, twist.angular.z])
        if times:
            return with_pitch(times, values, pitch, cfg), f'topic {cfg["topic"]}'

    times, values = [], []
    vx = vy = wz = 0.0
    pitch_value = cfg['pitch_default']
    arm_mode, last_toggle = False, None
    previous_buttons, previous_axes, previous_t = None, None, None
    for t, buttons, axes in joy_messages(reader, cfg['joy_topic']):
        if previous_t is not None and (t - previous_t) * 1e-9 > cfg['timeout_s']:
            # The controller zeroes the base reference after a joystick timeout.
            times.append(previous_t + int(cfg['timeout_s'] * 1e9))
            values.append([0.0, 0.0, 0.0, pitch_value])
            vx = vy = wz = 0.0
        if len(axes) >= cfg['min_axes']:
            if not arm_mode:
                alpha = cfg['filter']
                vx = vx * alpha + axes[cfg['vx_axis']] * cfg['vx_scale'] * (1 - alpha)
                vy = vy * alpha + axes[cfg['vy_axis']] * cfg['vy_scale'] * (1 - alpha)
                wz = wz * alpha + axes[cfg['wz_axis']] * cfg['wz_scale'] * (1 - alpha)
            axis = cfg['pitch_axis']
            if axis is not None and axis < len(axes):
                if cfg['pitch_mode'] == 'absolute':
                    pitch_value = axes[axis] * cfg['pitch_scale']
                elif previous_axes is not None and previous_t is not None:
                    dt = min((t - previous_t) * 1e-9, cfg['timeout_s'])
                    pitch_value += previous_axes[axis] * cfg['pitch_scale'] * dt
                pitch_value = float(np.clip(pitch_value, cfg['pitch_min'], cfg['pitch_max']))
            if rising_edge(buttons, previous_buttons, cfg['arm_mode_button']) and (
                last_toggle is None or (t - last_toggle) * 1e-9 >= cfg['debounce_s']
            ):
                arm_mode, last_toggle = not arm_mode, t
            times.append(t)
            values.append([vx, vy, wz, pitch_value])
        previous_buttons, previous_axes, previous_t = buttons, axes, t

    signal = Signal.from_lists(times, values, 4)
    if pitch is not None and len(signal.times):
        signal.values[:, 3] = [p[0] if (p := pitch.at(t)) is not None else cfg['pitch_default']
                               for t in signal.times]
    return signal, f'reconstructed from {cfg["joy_topic"]}'


def with_pitch(times, values, pitch, cfg):
    rows = []
    for t, row in zip(times, values, strict=True):
        p = pitch.at(t) if pitch is not None else None
        rows.append([*row, p[0] if p is not None else cfg['pitch_default']])
    return Signal.from_lists(times, rows, 4)


def decode_image(msgtype, msg):
    """Return an RGB uint8 (H, W, 3) or depth uint16 (H, W, 1) array."""
    data = np.frombuffer(bytes(msg.data), dtype=np.uint8)
    if msgtype == 'sensor_msgs/msg/CompressedImage':
        fmt = msg.format.lower()
        if 'compresseddepth' in fmt:
            # compressed_depth_image_transport: 12-byte config header + PNG.
            depth = cv2.imdecode(data[12:], cv2.IMREAD_UNCHANGED)
            return depth.astype(np.uint16)[..., None]
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    encoding = msg.encoding.lower()
    if encoding in ('16uc1', 'mono16'):
        return data.view(np.uint16).reshape(msg.height, msg.width, 1).copy()
    image = data.reshape(msg.height, msg.width, -1)
    if encoding == 'bgr8':
        image = image[..., ::-1]
    return np.ascontiguousarray(image[..., :3])


def resolve_cameras(reader, cfg, use_depth):
    topics = {c.topic: c for c in reader.connections}
    cameras = {}
    for name, candidates in cfg['cameras'].items():
        if not use_depth and name.endswith('_depth'):
            continue
        topic = next((t for t in candidates if t in topics), None)
        if topic is None:
            raise SystemExit(f'No topic found for camera {name!r}; tried: {candidates}')
        cameras[name] = topics[topic]
    return cameras


def probe_camera_shapes(reader, cameras):
    shapes = {}
    for name, connection in cameras.items():
        for _, _, raw in reader.messages(connections=[connection]):
            shapes[name] = decode_image(connection.msgtype, reader.deserialize(raw, connection.msgtype)).shape
            break
    return shapes


def build_features(shapes):
    features = {
        'action': {'dtype': 'float32', 'shape': (len(ACTION_NAMES),), 'names': ACTION_NAMES},
        'observation.state': {'dtype': 'float32', 'shape': (len(STATE_NAMES),), 'names': STATE_NAMES},
    }
    for name, shape in shapes.items():
        features[f'observation.images.{name}'] = {
            'dtype': 'video',
            'shape': tuple(shape),
            'names': ['height', 'width', 'channels'],
            'info': {'is_depth_map': shape[2] == 1},
        }
    return features


def load_tasks(args):
    if args.tasks_file:
        return yaml.safe_load(Path(args.tasks_file).read_text()) or {}
    return {}


def task_for(tasks, default, bag_name, index):
    entry = tasks.get(bag_name, default)
    if isinstance(entry, list):
        entry = entry[index] if index < len(entry) else default
    if not entry:
        raise SystemExit(f'No task for {bag_name} episode {index}; pass --task or --tasks-file.')
    return entry


class BagExporter:
    def __init__(self, bag, cfg, args):
        self.bag = Path(bag)
        self.cfg = cfg
        self.args = args
        self.period = int(round(1e9 / args.fps))

    def load(self, reader):
        cfg = self.cfg
        self.episodes, unfinished = find_episodes(reader, cfg)
        if unfinished:
            print(f'  {self.bag.name}: last episode has no end marker, skipped')
        self.cameras = resolve_cameras(reader, cfg, not self.args.no_depth)
        arm_command = cfg['arm_command']
        self.arm_command = read_joint_signal(reader, arm_command['topic'], arm_command['joints'])
        state_joints = [*cfg['arm_state']['joints'], cfg['arm_state']['gripper_joint']]
        self.arm_state = read_joint_signal(reader, cfg['arm_state']['topic'], state_joints)
        self.odometry = read_odometry(reader, cfg['odometry']['topic'])
        self.gripper = read_gripper_command(reader, cfg['gripper_command'])
        self.base, self.base_source = read_base_command(reader, cfg['base_command'])
        for label, signal in [('arm command', self.arm_command), ('arm state', self.arm_state),
                              ('odometry', self.odometry), ('gripper command', self.gripper),
                              ('base command', self.base)]:
            if not len(signal.times):
                raise SystemExit(f'{self.bag.name}: no {label} messages')

    def schedule(self, reader):
        """Assign sample times to episodes, starting once every stream has data."""
        firsts = [s.first_time() for s in (self.arm_command, self.arm_state, self.odometry)]
        for connection in self.cameras.values():
            first = next(reader.messages(connections=[connection]), None)
            firsts.append(first[1] if first else None)
        ready = max(firsts)
        min_frames = int(self.args.min_duration * self.args.fps)
        kept = []
        for episode in self.episodes:
            start = max(episode.start, ready)
            episode.times = list(range(start, episode.end + 1, self.period))
            if len(episode.times) >= max(min_frames, 1):
                kept.append(episode)
        self.episodes = kept

    def frame(self, t, images):
        base = self.base.at(t)
        if base is None:
            base = np.array([0.0, 0.0, 0.0, self.cfg['base_command']['pitch_default']])
        gripper = self.gripper.at(t)
        if gripper is None:
            gripper = [self.cfg['gripper_command']['low_value']]
        action = np.concatenate([base, self.arm_command.at(t), gripper])
        state = np.concatenate([self.arm_state.at(t), self.odometry.at(t)])
        frame = {
            'action': action.astype(np.float32),
            'observation.state': state.astype(np.float32),
        }
        for name, image in images.items():
            frame[f'observation.images.{name}'] = image
        return frame

    def export(self, reader, dataset, tasks, episode_offset):
        samples = [(t, i) for i, ep in enumerate(self.episodes) for t in ep.times]
        latest = {}
        decoded = {}
        cursor = 0
        by_connection = {c.id: name for name, c in self.cameras.items()}

        def emit(t, episode_index):
            images = {}
            for name in self.cameras:
                key = latest[name]
                if decoded.get(name, (None,))[0] != key:
                    connection, raw = key[1], key[2]
                    decoded[name] = (key, decode_image(connection.msgtype,
                                                       reader.deserialize(raw, connection.msgtype)))
                images[name] = decoded[name][1]
            frame = self.frame(t, images)
            frame['task'] = task_for(tasks, self.args.task, self.bag.name, episode_index)
            dataset.add_frame(frame)
            episode = self.episodes[episode_index]
            if t == episode.times[-1]:
                dataset.save_episode()
                print(f'  episode {episode_offset + episode_index}: {self.bag.name} '
                      f'[{(episode.start - self.t0) * 1e-9:.1f}s, {(episode.end - self.t0) * 1e-9:.1f}s] '
                      f'{len(episode.times)} frames')

        if not samples:
            return 0
        for connection, t, raw in reader.messages(connections=list(self.cameras.values())):
            while cursor < len(samples) and samples[cursor][0] < t:
                emit(*samples[cursor])
                cursor += 1
            if cursor == len(samples):
                break
            latest[by_connection[connection.id]] = (t, connection, raw)
        while cursor < len(samples):
            emit(*samples[cursor])
            cursor += 1
        return len(self.episodes)

    def run(self, dataset, tasks, episode_offset):
        with AnyReader([self.bag]) as reader:
            self.t0 = reader.start_time
            self.load(reader)
            self.schedule(reader)
            print(f'{self.bag.name}: {len(self.episodes)} episodes, base command {self.base_source}')
            if dataset is None:
                for i, ep in enumerate(self.episodes):
                    print(f'  episode {episode_offset + i}: [{(ep.start - self.t0) * 1e-9:.1f}s, '
                          f'{(ep.end - self.t0) * 1e-9:.1f}s] {len(ep.times)} frames, '
                          f'task: {task_for(tasks, self.args.task, self.bag.name, i)}')
                return len(self.episodes)
            return self.export(reader, dataset, tasks, episode_offset)


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('bags', nargs='+', type=Path, help='rosbag2 directories')
    parser.add_argument('--repo-id', required=True, help='dataset id, e.g. user/go2piper_pickplace')
    parser.add_argument('--root', type=Path, help='output directory (default: $HF_LEROBOT_HOME/<repo-id>)')
    parser.add_argument('--task', help='language instruction for every episode')
    parser.add_argument('--tasks-file',
                        help='YAML mapping bag name to a task, or to a list of tasks per episode')
    parser.add_argument('--config', help='YAML file overriding DEFAULT_CONFIG')
    parser.add_argument('--fps', type=int, default=10)
    parser.add_argument('--gripper-button', type=int, help='override gripper_command.button')
    parser.add_argument('--no-depth', action='store_true', help='export colour images only')
    parser.add_argument('--min-duration', type=float, default=1.0, help='drop shorter episodes (s)')
    parser.add_argument('--overwrite', action='store_true', help='replace an existing output directory')
    parser.add_argument('--dry-run', action='store_true', help='list episodes without writing')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if args.config:
        deep_update(cfg, yaml.safe_load(Path(args.config).read_text()) or {})
    if args.gripper_button is not None:
        cfg['gripper_command']['button'] = args.gripper_button
    tasks = load_tasks(args)

    dataset = None
    if not args.dry_run:
        from lerobot.datasets.lerobot_dataset import LeRobotDataset

        with AnyReader([args.bags[0]]) as reader:
            shapes = probe_camera_shapes(reader, resolve_cameras(reader, cfg, not args.no_depth))
        if args.root and args.root.exists():
            if not args.overwrite:
                raise SystemExit(f'{args.root} exists; pass --overwrite to replace it')
            shutil.rmtree(args.root)
        dataset = LeRobotDataset.create(
            repo_id=args.repo_id,
            fps=args.fps,
            features=build_features(shapes),
            root=args.root,
            robot_type=cfg['robot_type'],
            image_writer_threads=4,
        )

    total = 0
    try:
        for bag in args.bags:
            total += BagExporter(bag, cfg, args).run(dataset, tasks, total)
    finally:
        if dataset is not None:
            dataset.finalize()
    print(f'{total} episodes' + ('' if dataset is None else f' written to {dataset.root}'))


if __name__ == '__main__':
    sys.exit(main())
