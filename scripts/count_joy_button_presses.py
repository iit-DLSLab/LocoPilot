#!/usr/bin/env python3
# Copyright 2026 Istituto Italiano di Tecnologia
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Count Joy button rising edges in one or more ROS 2 bags.

For example:
    python count_joy_button_presses.py bag_1 bag_2 --topic joycon
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Optional, Sequence

try:
    from rosbags.highlevel import AnyReader
except ImportError as exc:  # pragma: no cover - import guard for users.
    raise SystemExit(
        'This script requires rosbags. Install it with: '
        'python -m pip install rosbags'
    ) from exc


@dataclass
class ButtonPressStats:
    """Button press counts for one bag."""

    bag_path: Path
    topic: str
    message_count: int = 0
    button_count: int = 0
    presses_by_button: Counter[int] = field(default_factory=Counter)
    pressed_messages_by_button: Counter[int] = field(default_factory=Counter)

    @property
    def press_count(self) -> int:
        """Return the total number of button rising edges."""
        return sum(self.presses_by_button.values())


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the command-line tool."""
    args = _parse_args(argv)
    requested_topic = _canonical_topic(args.topic)
    stats = [count_button_presses(path, requested_topic) for path in args.bags]
    _print_report(stats)
    return 0


def count_button_presses(bag_path: Path, topic: str) -> ButtonPressStats:
    """Count button transitions from unpressed to pressed in ``bag_path``."""
    if not bag_path.exists():
        raise FileNotFoundError(f'Bag path does not exist: {bag_path}')

    with AnyReader([bag_path]) as reader:
        connections = [
            connection for connection in reader.connections if connection.topic == topic
        ]
        if not connections:
            available_topics = ', '.join(
                sorted(connection.topic for connection in reader.connections)
            )
            raise ValueError(
                f'Topic {topic!r} was not found in {bag_path}. '
                f'Available topics: {available_topics}'
            )

        non_joy_connections = [
            connection
            for connection in connections
            if connection.msgtype != 'sensor_msgs/msg/Joy'
        ]
        if non_joy_connections:
            msgtypes = ', '.join(
                sorted({connection.msgtype for connection in non_joy_connections})
            )
            raise ValueError(
                f'Topic {topic!r} in {bag_path} is not sensor_msgs/msg/Joy '
                f'(found {msgtypes}).'
            )

        stats = ButtonPressStats(bag_path=bag_path, topic=topic)
        previous_buttons: list[bool] = []
        for connection, _, rawdata in reader.messages(connections=connections):
            message = reader.deserialize(rawdata, connection.msgtype)
            buttons = [bool(button) for button in message.buttons]
            stats.button_count = max(stats.button_count, len(buttons))
            for index, is_pressed in enumerate(buttons):
                if is_pressed:
                    stats.pressed_messages_by_button[index] += 1
                was_pressed = (
                    previous_buttons[index] if index < len(previous_buttons) else False
                )
                if is_pressed and not was_pressed:
                    stats.presses_by_button[index] += 1
            previous_buttons = buttons
            stats.message_count += 1

    return stats


def _print_report(stats_by_bag: Sequence[ButtonPressStats]) -> None:
    """Print per-bag and aggregate counts."""
    aggregate_presses = Counter()
    aggregate_pressed_messages = Counter()
    aggregate_button_count = 0
    total_messages = 0
    for stats in stats_by_bag:
        aggregate_presses.update(stats.presses_by_button)
        aggregate_pressed_messages.update(stats.pressed_messages_by_button)
        aggregate_button_count = max(aggregate_button_count, stats.button_count)
        total_messages += stats.message_count
        print(stats.bag_path)
        print(f'  topic: {stats.topic}')
        print(f'  Joy messages: {stats.message_count}')
        print(f'  button presses: {stats.press_count}')
        _print_button_diagnostics(
            stats.button_count,
            stats.presses_by_button,
            stats.pressed_messages_by_button,
            indent='    ',
        )

    if len(stats_by_bag) > 1:
        print('Aggregate')
        print(f'  bags: {len(stats_by_bag)}')
        print(f'  Joy messages: {total_messages}')
        print(f'  button presses: {sum(aggregate_presses.values())}')
        _print_button_diagnostics(
            aggregate_button_count,
            aggregate_presses,
            aggregate_pressed_messages,
            indent='    ',
        )


def _print_button_diagnostics(
    button_count: int,
    presses_by_button: Counter[int],
    pressed_messages_by_button: Counter[int],
    indent: str,
) -> None:
    """Print diagnostics for every zero-based button index."""
    if button_count == 0:
        print(f'{indent}by button: none')
        return
    print(f'{indent}by button:')
    for button_index in range(button_count):
        print(
            f'{indent}  {button_index}: '
            f'presses={presses_by_button[button_index]}, '
            f'pressed_messages={pressed_messages_by_button[button_index]}'
        )


def _canonical_topic(topic: str) -> str:
    """Accept topic names with or without their leading slash."""
    return topic if topic.startswith('/') else f'/{topic}'


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'bags',
        nargs='+',
        type=Path,
        help='ROS 2 bag directories or MCAP bag files to inspect.',
    )
    parser.add_argument(
        '--topic',
        default='joycon',
        help='Joy topic to inspect (default: joycon).',
    )
    return parser.parse_args(argv)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (FileNotFoundError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(2)
