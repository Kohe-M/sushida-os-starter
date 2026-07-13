FROM debian:trixie

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bats \
    ca-certificates \
    git \
    jq \
    live-build \
    make \
    python3 \
    python3-pytest \
    shellcheck \
    systemd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /sushida-os

COPY builder/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
