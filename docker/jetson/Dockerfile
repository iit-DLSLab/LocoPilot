# syntax=docker/dockerfile:1.7
# Jetson (robot-side) arm teleoperation image. Build ON the robot with
# jetson/build-image.sh; the base image is the arm64 ros:jazzy-ros-base
# produced by jetson-containers (see docker/README.md, "Jetson image").
#
# Build context is the parent docker/ directory so the in-container scripts
# (dls-env, entrypoint, can-activate, teleop-session, vla-session) are shared with the
# laptop image:  docker build -f jetson/Dockerfile <docker dir>
ARG BASE_IMAGE=ros:jazzy-ros-base
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    ROS_DOMAIN_ID=0 \
    ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONNOUSERSITE=1 \
    PATH=/opt/deploy_venv/bin:${PATH}

# ROS 2 Jazzy comes from the jetson-containers base. This layer adds build
# tools, the Piper arm / demo-recorder runtime packages, CAN tooling, and the
# RealSense camera stack.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    git-lfs \
    pkg-config \
    python3-dev \
    python3-pip \
    python3-venv \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool \
    iproute2 \
    iputils-ping \
    net-tools \
    ethtool \
    usbutils \
    procps \
    psmisc \
    sudo \
    tmux \
    vim-tiny \
    can-utils \
    python3-can \
    python3-serial \
    python3-scipy \
    python3-typing-extensions \
    ros-jazzy-rmw-fastrtps-cpp \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-robot-state-publisher \
    ros-jazzy-joint-state-publisher \
    ros-jazzy-joint-state-publisher-gui \
    # rviz2 is required even headless: agx_arm_description's display.launch.py
    # (included by start_single_agx_arm_rviz.launch.py) declares an rviz2 node
    # unconditionally, and launch aborts if the package is missing. Without a
    # DISPLAY the rviz2 process exits; the arm nodes keep running.
    ros-jazzy-rviz2 \
    ros-jazzy-xacro \
    ros-jazzy-moveit-msgs \
    # moveit_configs_utils: vla_arm_controllers.launch.py imports
    # agx_arm_moveit's own MoveItConfigsBuilder-based robot_description
    # builder, so the VLA ros2_control_node gets the identical URDF the real
    # MoveIt launch (demo.launch.py) uses. Does not pull in move_group/rviz.
    ros-jazzy-moveit-configs-utils \
    # ros2_control stack for the VLA deploy (vla-session): controller_manager +
    # mock_components (ros2-control) and the joint_trajectory / joint_state
    # broadcaster controllers (ros2-controllers). Teleop does not use these.
    ros-jazzy-ros2-control \
    ros-jazzy-ros2-controllers \
    ros-jazzy-topic-tools \
    ros-jazzy-generate-parameter-library \
    ros-jazzy-generate-parameter-library-py \
    ros-jazzy-librealsense2 \
    ros-jazzy-realsense2-camera-msgs \
    ros-jazzy-realsense2-camera \
    # image_transport plugin so the RealSense image topics also advertise
    # lossless /zstd variants (picked up by the camera node at runtime)
    ros-jazzy-zstd-image-transport \
    && rm -rf /var/lib/apt/lists/*

RUN rosdep init 2>/dev/null || true \
    && rosdep update --rosdistro jazzy

COPY jetson/requirements-jetson.txt /tmp/requirements-jetson.txt
# Do NOT upgrade setuptools here (same constraint as the laptop image).
RUN python3 -m venv --system-site-packages /opt/deploy_venv \
    && /opt/deploy_venv/bin/python -m pip install --upgrade pip wheel \
    && /opt/deploy_venv/bin/python -m pip install \
        -r /tmp/requirements-jetson.txt

COPY docker/dls-env /usr/local/bin/dls-env
COPY docker/entrypoint.sh /usr/local/bin/dls-entrypoint
COPY docker/build-extra-workspace /usr/local/bin/build-extra-workspace
COPY docker/can-activate /usr/local/bin/can-activate
COPY docker/teleop-session /usr/local/bin/teleop-session
COPY docker/vla-session /usr/local/bin/vla-session
COPY jetson/docker/build-jetson-workspaces /usr/local/bin/build-jetson-workspaces

RUN chmod +x \
    /usr/local/bin/dls-env \
    /usr/local/bin/dls-entrypoint \
    /usr/local/bin/build-extra-workspace \
    /usr/local/bin/can-activate \
    /usr/local/bin/teleop-session \
    /usr/local/bin/vla-session \
    /usr/local/bin/build-jetson-workspaces \
    && printf '\n# DLS Jazzy deployment environment\nsource /usr/local/bin/dls-env\n' >> /root/.bashrc \
    && printf 'set -g mouse on\nset -g set-clipboard on\n' >> /root/.tmux.conf

WORKDIR /workspace/locoman_vla_deploy
ENTRYPOINT ["/usr/local/bin/dls-entrypoint"]
CMD ["sleep", "infinity"]
