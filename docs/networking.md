# Networking

## Wired Ethernet

NetworkManager is configured to manage Ethernet interfaces via
`/etc/NetworkManager/conf.d/90-sushida-os.conf`.

Configuration:

```ini
[main]
plugins=ifupdown,keyfile

[ifupdown]
managed=true
```

- Plugins `ifupdown` and `keyfile` are enabled.
- `managed=true` allows NetworkManager to control interfaces defined in
  `/etc/network/interfaces`.
- Wired Ethernet uses NetworkManager's default DHCP auto-connect profile.
- No static IP, DNS, proxy, or interface-name overrides are set.

Wired DHCP behavior requires QEMU or hardware to verify.

## Optional Wi-Fi

### Build-time staging

Wi-Fi credentials are provided through the untracked file
`local/wifi.nmconnection`.  When present during `make configure`, it is
staged into the build tree at:

```
build/live-build/config/includes.chroot/etc/NetworkManager/system-connections/sushida-os-wifi.nmconnection
```

The file is installed with mode `0600` and ownership `root:root`.
Placeholder values (`REPLACE_WITH_*`) cause the chroot hook to fail.

If `local/wifi.nmconnection` does not exist, no Wi-Fi profile is included.

### Credential extraction risk

Credentials embedded in an ISO can be extracted by anyone who obtains the
ISO.  A dedicated or least-privilege Wi-Fi credential is recommended.

### Updating credentials

Replace `local/wifi.nmconnection` and rebuild the ISO.  There is no Wi-Fi
settings GUI in the production image.

## Offline behaviour and recovery

Offline detection and automatic recovery are implemented by the network
watcher (Task 11).  The local offline page at
`file:///usr/share/sushida-os/offline.html` is displayed while the network
is unavailable.

## NetworkManager services

- `NetworkManager.service` is enabled at build time.
- `NetworkManager-wait-online.service` is not explicitly enabled; its role
  is evaluated during the offline-design task (Task 11).

## Verifying network behaviour

The following require QEMU or physical hardware:

- Wired Ethernet DHCP obtains an address and provides connectivity.
- Wi-Fi association works with a staged credential.
- Network recovery transition described in Task 11.
- Absence of unexpected network connections.
