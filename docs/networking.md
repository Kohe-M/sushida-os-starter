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

The network watcher checks `nmcli -t -f STATE general` at a default interval of
30 seconds. Only NetworkManager's exact global `connected` state is online; it
does not use `curl`, `wget`, `ping`, DNS probes, or requests to Sushi-da. The
local offline page at
`file:///usr/share/sushida-os/offline.html` is displayed while the network
is unavailable, and the validated configured official URL is selected after
recovery. The launcher performs this selection before starting Chromium and
atomically records `online` or `offline` in `/run/sushida-os/active-route`.

The watcher never invokes Chromium. When the recorded route differs from the
current NetworkManager state, it obtains `sushida-kiosk.service`'s `MainPID`
and validates that the PID exists, is owned by the watcher UID, and belongs to
the exact kiosk service cgroup. It then sends `TERM` to that PID. The unit's
`Restart=always` starts a fresh managed Cage/Chromium session, and the launcher
selects the new route. Missing or invalid markers, PID metadata, ownership, or
cgroup data fail closed without signalling a process. BATS covers these
transitions and rejection paths.

## NetworkManager services

- `NetworkManager.service` is enabled at build time.
- `sushida-network-watch.service` is enabled and ordered after the kiosk service
  and NetworkManager ordering constraints.

## Verifying network behaviour

The following require QEMU or physical hardware:

- Wired Ethernet DHCP obtains an address and provides connectivity.
- Wi-Fi association works with a staged credential.
- Network recovery from the offline page to the configured official URL.
- Absence of unexpected network connections.
