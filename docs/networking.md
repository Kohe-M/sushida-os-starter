# Networking

## Startup behaviour

NetworkManager manages both Ethernet and Wi-Fi. Wired Ethernet uses its default
DHCP auto-connect profile and therefore needs no UI. NetworkManager's built-in
connectivity check runs at most once every 300 seconds against its dedicated
status endpoint. At startup the launcher waits up to
`NETWORK_SETUP_GRACE_SECONDS` (15 seconds by default) for
`nmcli -t -f STATE,CONNECTIVITY general` to report `connected:full`.

- If connected, Chromium opens the configured official Sushi-da URL.
- If not connected, Chromium opens the local Wi-Fi setup service at
  `http://127.0.0.1:8787/`.
- If that service is unavailable, Chromium falls back to the static local
  network-unavailable page.

The network watcher reads the cached NetworkManager connectivity state every 30
seconds. `full` selects the official page; `portal`, `limited`, `none`, or an
unavailable query selects the setup/offline route. The watcher does not issue
its own DNS, ping, or HTTP probe and never requests Sushi-da. When the desired
route changes, it validates and terminates only the managed kiosk service
`MainPID`; systemd then starts a fresh Cage/Chromium session on the new route.

## On-device Wi-Fi setup

When the setup screen appears, select a scanned SSID from the large radio-button
rows and enter its password. The UI intentionally avoids native drop-down
popups because they are not reliable across all Cage/Wayland hardware paths.
`再スキャン` submits back to the setup page root and performs a fresh scan;
the page does not refresh automatically while a credential is being entered.
The setup backend asks NetworkManager to associate, enables auto-connect, and
stores the credential only after association succeeds. Open networks are
supported with an empty password. Hidden SSIDs and enterprise/802.1X networks
are not supported by this screen.

The password is supplied to `nmcli --ask` over a private standard-input pipe;
it is never placed in the `nmcli` command line where another local account
could read it through `/proc`. A WPA personal passphrase is accepted at 8–63
UTF-8 bytes, and a 64-digit hexadecimal raw PSK is also accepted. After a
successful activation, the backend returns a lightweight transition message
without performing another forced scan. The low-frequency route watcher then
restarts the kiosk onto the official URL.

Saved-credential restoration and an interactive connection request can overlap
during startup. The backend serializes those operations around the single
managed NetworkManager profile, preventing one request from deleting the
profile just created by the other. NetworkManager output is decoded
defensively; an SSID containing undecodable bytes is omitted instead of
breaking the entire scan response.

An active Ethernet route does not suppress saved Wi-Fi restoration. The
backend skips restoration only when its own fixed Wi-Fi profile is already
active, so Wi-Fi remains available as a fallback if Ethernet is unplugged
later. Failure or timeout while setting NetworkManager's auto-connect flag does
not tear down an otherwise successful HTTP response: the private
`SUSHIDA-CFG` credential remains the reboot recovery path. HTTP request bodies
also have a short read deadline and must match their declared size, preventing
one abandoned loopback POST from blocking all later rescans.

This is a constrained kiosk page, not a general network settings application:

- it listens only on `127.0.0.1:8787`;
- Chromium policy permits only that exact origin in addition to Sushi-da and
  the static offline page;
- requests require same-origin checks and a private runtime CSRF token;
- the dedicated `wifi-setup` account has a locked password, no shell, no
  supplementary groups, no capabilities, and no access to the kiosk profile;
- polkit grants that account only NetworkManager network control, system
  connection modification, and Wi-Fi radio control;
- the service cannot bind or connect outside loopback directly; NetworkManager's
  separate low-frequency connectivity checker is the only configured external
  status request.

After connection, the watcher replaces the setup session with the official
site. If a saved credential later fails, the setup screen returns and a new
successful entry replaces it. If NetworkManager changes to `connected` while
the setup page is already visible, the SSID rows, password field, and connect
button remain interactive until the watcher replaces that kiosk session. This
avoids an inert page during the startup race. There is intentionally no route
from the official site to a general settings screen.

Unknown local GET paths redirect to the setup root rather than leaving the
kiosk on a plain `Not found` response. Request diagnostics record only the HTTP
method and status in the volatile journal; paths, SSIDs, and credentials are
not logged.

The CSRF token is a private mode-`0600` file in the service's systemd runtime
directory. `RuntimeDirectoryPreserve=restart` keeps it across an automatic
backend restart, so a setup form that is already visible does not immediately
become stale. An explicit service stop or reboot still replaces the token. If
a stale token or an invalid browser origin is received, the response remains a
complete setup page with an actionable Japanese error instead of a plain white
`Forbidden` page; the submitted password is never reflected. Chromium normally
sends the exact loopback `Origin`. If it omits that header, the backend accepts
only the fixed loopback `Host` combined with `Sec-Fetch-Site: same-origin`, and
the CSRF token remains mandatory.

## Persistent credential boundary

The generated hybrid image contains a separate 64 MiB ext4 partition labelled
`SUSHIDA-CFG`. When the image is written to a USB flash drive, systemd mounts it
at `/var/lib/sushida-config` using
`rw,nodev,nosuid,noexec,noatime`. The only persistent application file is a
mode-`0600` Wi-Fi credential owned by `wifi-setup`. Browser profiles, caches,
downloads, home state, logs, and the live root overlay remain volatile.

The root-owned preparation service publishes only a boot-lifetime readiness
marker at `/run/sushida-config/config-storage`. This directory is independent
of `/run/sushida-os`, which systemd removes and recreates whenever the kiosk
session restarts during a network-route transition. The separation prevents a
kiosk restart from silently downgrading later Wi-Fi changes to session-only
connections. The marker is replaced atomically, and both the preparation
service and backend reject unsafe file modes, owners, symbolic links, and
non-directory configuration paths.

The root SquashFS never becomes writable and the partition is not a live-boot
persistence volume. If the partition is missing, read-only, not ext4, or cannot
be mounted, boot continues. The setup page remains interactive and can establish
a connection for the current boot, but clearly reports that it cannot preserve
that connection across a reboot. The mount unit waits briefly for the stable
filesystem label instead of making a one-shot early path check, avoiding a race
with udev while still keeping a missing partition non-fatal. The static offline
page remains the final fallback.

Credentials on `SUSHIDA-CFG` are plaintext configuration data. Anyone who
obtains the USB device or ISO can extract them. Use a dedicated, least-privilege
Wi-Fi network and control physical access and artifact distribution. The design
does not claim protection against a physical attacker.

## Optional build-time profile

For pre-provisioned deployments, an untracked `local/wifi.nmconnection` may
still be supplied before `make configure`. It is staged as a root-owned
mode-`0600` NetworkManager system connection. Placeholder values fail the image
build, and no profile is included when the file is absent. Never commit real
credentials. The same extraction warning applies to build-time profiles.

## Verification

Repository tests verify the state machine, serialized NetworkManager changes,
wired-to-Wi-Fi fallback restoration, secret delivery outside process arguments,
bounded HTTP reads, post-connection timeout recovery, input validation,
malformed scan output, atomic credential/status writes, symlink refusal, file
modes, service sandboxing, polkit scope, Chromium origin, and ISO partition
structure. QEMU can verify that a writable copy of the hybrid image
boots, mounts `SUSHIDA-CFG`, and starts the setup services. The isolated QEMU
smoke entry deliberately shows the static offline page: its virtual NIC is not
a Wi-Fi device, and the loopback Chromium path is unreliable under TCG-only
emulation. The following remain physical-hardware acceptance items:

- Ethernet DHCP and route recovery;
- Wi-Fi scan and association on each supported adapter;
- credential survival across a clean reboot;
- replacement after an incorrect or changed password;
- recovery after power loss during or after a credential update;
- absence of unexpected external network requests.
