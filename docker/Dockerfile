# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE=osrf/ros:jazzy-desktop
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

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

# ROS 2 Jazzy comes from the base image. This layer adds build tools, the
# deployment-time ROS packages, MUSE dependencies, robot/network tools, and
# libraries required by MuJoCo's viewer.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    git-lfs \
    ninja-build \
    pkg-config \
    python3-dev \
    python3-pip \
    python3-venv \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool \
    libeigen3-dev \
    libyaml-cpp-dev \
    libboost-all-dev \
    libgl1 \
    libgl1-mesa-dri \
    libglfw3 \
    libglfw3-dev \
    libx11-6 \
    libxcursor1 \
    libxinerama1 \
    libxi6 \
    libxrandr2 \
    libxkbcommon-x11-0 \
    mesa-utils \
    iproute2 \
    iputils-ping \
    net-tools \
    ethtool \
    usbutils \
    joystick \
    procps \
    psmisc \
    sudo \
    tmux \
    vim-tiny \
    ros-jazzy-rmw-fastrtps-cpp \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-rosidl-generator-dds-idl \
    ros-jazzy-message-filters \
    ros-jazzy-robot-state-publisher \
    ros-jazzy-joint-state-publisher \
    ros-jazzy-xacro \
    ros-jazzy-joy \
    ros-jazzy-teleop-twist-joy \
    ros-jazzy-plotjuggler-ros \
    ros-jazzy-pinocchio \
    ros-jazzy-pcl-ros \
    ros-jazzy-librealsense2 \
    ros-jazzy-realsense2-camera-msgs \
    ros-jazzy-realsense2-camera \
    # image_transport plugin so the RealSense image topics also advertise
    # lossless /zstd variants (picked up by the camera node at runtime)
    ros-jazzy-zstd-image-transport \
    liburdfdom-headers-dev \
    can-utils \
    python3-can \
    python3-serial \
    python3-scipy \
    python3-typing-extensions \
    ros-jazzy-joint-state-publisher-gui \
    ros-jazzy-moveit \
    ros-jazzy-moveit-msgs \
    ros-jazzy-ros2-control \
    ros-jazzy-ros2-controllers \
    ros-jazzy-topic-tools \
    ros-jazzy-generate-parameter-library \
    ros-jazzy-generate-parameter-library-py \
    && rm -rf /var/lib/apt/lists/*

RUN rosdep init 2>/dev/null || true \
    && rosdep update --rosdistro jazzy

COPY requirements-deploy.txt /tmp/requirements-deploy.txt
# Do NOT upgrade setuptools here
RUN python3 -m venv --system-site-packages /opt/deploy_venv \
    && /opt/deploy_venv/bin/python -m pip install --upgrade pip wheel \
    && /opt/deploy_venv/bin/python -m pip install \
        --index-url "${TORCH_INDEX_URL}" torch \
    && /opt/deploy_venv/bin/python -m pip install \
        -r /tmp/requirements-deploy.txt

COPY docker/dls-env /usr/local/bin/dls-env
COPY docker/entrypoint.sh /usr/local/bin/dls-entrypoint
COPY docker/build-dls-workspaces /usr/local/bin/build-dls-workspaces
COPY docker/build-extra-workspace /usr/local/bin/build-extra-workspace
COPY docker/run-go2-hal /usr/local/bin/run-go2-hal
COPY docker/run-piper-hal /usr/local/bin/run-piper-hal
COPY docker/run-muse /usr/local/bin/run-muse
COPY docker/run-controller /usr/local/bin/run-controller
COPY docker/run-joy /usr/local/bin/run-joy
COPY docker/check-stack /usr/local/bin/check-stack
COPY docker/can-activate /usr/local/bin/can-activate
COPY docker/teleop-session /usr/local/bin/teleop-session

RUN chmod +x \
    /usr/local/bin/dls-env \
    /usr/local/bin/dls-entrypoint \
    /usr/local/bin/build-dls-workspaces \
    /usr/local/bin/build-extra-workspace \
    /usr/local/bin/run-go2-hal \
    /usr/local/bin/run-piper-hal \
    /usr/local/bin/run-muse \
    /usr/local/bin/run-controller \
    /usr/local/bin/run-joy \
    /usr/local/bin/check-stack \
    /usr/local/bin/can-activate \
    /usr/local/bin/teleop-session \
    && printf '\n# DLS Jazzy deployment environment\nsource /usr/local/bin/dls-env\n' >> /root/.bashrc \
    && printf 'set -g mouse on\nset -g set-clipboard on\n' >> /root/.tmux.conf

WORKDIR /workspace/locoman_vla_deploy
ENTRYPOINT ["/usr/local/bin/dls-entrypoint"]
CMD ["sleep", "infinity"]
