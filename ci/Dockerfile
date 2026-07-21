# Template Vitis image for the self-hosted integration job.
#
# AMD's license terms forbid redistributing the Vitis installer, so you must 
# download it yourself and build the image locally. The finished image is 130+ GB 
# and can take over an hour to build. It's recommended to cache the build in a 
# registry rather than rebuilding per run. For maintained, layered recipes across 
# Vitis versions, see https://gitlab.com/rjmoss/xilinx-docker.
#
# Build (from a directory holding the extracted Vitis web installer):
#   docker build -f ci/Dockerfile -t vitis:2024.1 \
#     --build-arg VITIS_VERSION=2024.1 .

FROM ubuntu:22.04

ARG VITIS_VERSION=2024.1
ARG VITIS_INSTALL_DIR=/opt/Xilinx

# Dependencies the Vitis installer and the embedded toolchain need. The exact
# list tracks the AMD "installation requirements" for your version, this covers
# the common requirements.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates libtinfo5 libncurses5 libncursesw5 \
        locales x11-apps x11-utils xvfb git make ninja-build cmake \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8

# Copy the extracted installer and an unattended install config. Generate the
# config with `xsetup -b ConfigGen` and trim it to the Vitis Embedded edition to
# keep the image as small as possible.
COPY installer/ /tmp/vitis-installer/
COPY install_config.txt /tmp/install_config.txt

RUN /tmp/vitis-installer/xsetup \
        --agree XilinxEULA,3rdPartyEULA \
        --batch Install \
        --config /tmp/install_config.txt \
        --location ${VITIS_INSTALL_DIR} \
    && rm -rf /tmp/vitis-installer /tmp/install_config.txt

# Put vitis, xsct, and the bundled tools on PATH. `Do` only needs `vitis`.
ENV PATH="${VITIS_INSTALL_DIR}/Vitis/${VITIS_VERSION}/bin:${PATH}"

# For devices that require a license, set this at runtime:
#   docker run -e XILINXD_LICENSE_FILE=2100@license-server ...

CMD ["bash"]
