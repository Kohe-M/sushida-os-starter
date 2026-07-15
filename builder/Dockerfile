FROM debian:trixie

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bats \
    ca-certificates \
    debootstrap \
    dosfstools \
    git \
    grub-efi-amd64-bin \
    grub-pc-bin \
    isolinux \
    jq \
    live-build \
    make \
    mtools \
    python3 \
    python3-pytest \
    qemu-system-x86 \
    shellcheck \
    socat \
    squashfs-tools \
    syslinux-common \
    systemd \
    ovmf \
    xorriso \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /sushida-os

COPY builder/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
