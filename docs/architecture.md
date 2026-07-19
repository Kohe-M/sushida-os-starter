# Architecture

## Runtime chain

```text
bootloader
  -> Debian live system
  -> systemd
  -> SUSHIDA-CFG mount + constrained Wi-Fi setup backend
  -> sushida-kiosk.service
  -> sushida-launch
  -> dbus-run-session
  -> sushida-session
  -> PipeWire + WirePlumber + Cage
  -> Chromium kiosk window
  -> official Sushi-da URL
```

The keyboard boundary is configured before the session starts: the image's
`/etc/default/keyboard` and generated console-setup cache use `pc105`/`jp`/
`106`, while `sushida-kiosk.service` exports the matching `XKB_DEFAULT_*`
variables inherited by Cage and Chromium. No input interception or general
settings GUI is installed.

Power-button shutdown is delegated to `systemd-logind`. The kiosk image sets
`HandlePowerKey=poweroff`, `PowerKeyIgnoreInhibited=yes`, ignores long presses,
disables automatic VTs, and does not install an ACPI event daemon or enable a
separate poweroff target.
The normal systemd poweroff transaction therefore unmounts `SUSHIDA-CFG`; a
QEMU-only monitor test sends `system_powerdown` to an isolated guest socket and
requires natural exit without affecting the host.

## Read-only live-system boundary

The production ISO uses Debian live-boot without a persistent root. Its source
filesystem is an immutable SquashFS image.  live-boot supplies a volatile overlay
so software can perform normal runtime writes, but that writable layer
is held in memory and is discarded at shutdown or reboot.  This is not a claim
that every path is mounted with the VFS `ro` flag after boot; the security and
recovery property is that no writable persistent root layer is configured.

The image does not enable a live-boot persistence label, persistence
configuration file, or persistent home. A sudden power loss therefore discards
the volatile root overlay and the next boot starts from the signed-off image
contents. A separate 64 MiB ext4 partition labelled `SUSHIDA-CFG` persists only
the selected Wi-Fi credential; it is not an overlay and cannot modify the
SquashFS root. Firmware, the ISO/USB medium, and physical storage remain outside
this software boundary.

Expected mutable kiosk state is placed explicitly under `/run`, which systemd
mounts as tmpfs:

| State | Runtime destination | Persistence |
|---|---|---|
| Chromium profile | `/run/sushida-os/chromium` | None |
| Chromium cache | `/run/sushida-os/cache` | None |
| Downloads/temp files | `/run/sushida-os/downloads`, `/run/sushida-os/tmp` | None |
| Synthetic home | `/run/sushida-os/home` | None |
| Wayland/PipeWire/session sockets | `/run/sushida-os/xdg-runtime` | None |
| Selected network route | `/run/sushida-os/active-route` | None |
| Config-storage readiness | `/run/sushida-config/config-storage` | None |
| Wi-Fi credential | `/var/lib/sushida-config/network/setup.json` | `SUSHIDA-CFG` only |
| system journal | `/run/log/journal` (`Storage=volatile`) | None |

`systemd-tmpfiles` creates the kiosk directories as `kiosk:kiosk`, mode 0700
(the parent is 0750).  The kiosk service also uses `RuntimeDirectory` as a
startup safety net.  No persistent browser profile or kiosk home is created.

## Security boundaries

Navigation is restricted at two independent layers.

### Layer 1: Launcher (sushida-launch)

The launcher parses `/etc/sushida-os/config.env`, validates the configured
`SUSHIDA_URL`, waits a bounded period for NetworkManager's connectivity state,
and selects the
official URL, fixed loopback setup URL, or static offline fallback before
passing it to Chromium. Only configured URLs
matching the following patterns are accepted:

This selection is repeated after startup whenever the low-frequency network
watcher detects a route-state change and restarts only the managed kiosk
session. The independently supervised loopback Wi-Fi backend remains available,
so setup is not a first-boot-only path. There is intentionally no settings
navigation from the official page while NetworkManager reports full
connectivity.

- `https://sushida.net` — bare domain
- `https://sushida.net/` — bare domain with slash
- `https://sushida.net/*` — any path under the official domain

Rejected:

- `http://` (any host)
- Other HTTPS hosts
- Subdomains of sushida.net (e.g. `sub.sushida.net`)
- Username/password in URL (`https://user:pass@host/`)
- Non-standard port
- `javascript:`, `data:`, `file:` schemes

### Layer 2: Managed Chromium policy

Chromium's `URLAllowlist` and `URLBlocklist` policies enforce a second
origin boundary inside the browser.  Even if the launcher were bypassed,
the policy blocks forbidden URLs.

The allowlist contains:

| Entry | Purpose |
|---|---|
| `https://.sushida.net:443` | Sushi-da origin, port 443, all paths |
| `file:///usr/share/sushida-os/offline.html` | Local offline page policy pattern |
| `http://127.0.0.1:8787` | Constrained on-device Wi-Fi setup origin, port fixed |

`https://.sushida.net:443` uses the following Chromium URL filter
conventions (see [Chromium URL filter format][url-filter-format]):

- Leading dot (`.sushida.net`) — exact host match, no subdomains.
- Explicit port (`:443`) — restricts to the standard HTTPS port only.
- Omitted path component — matches any path under the origin.

Chromium's file URL policy grammar requires an empty authority and three
slashes after `file:`. This pattern matches the runtime URL
`file://localhost/usr/share/sushida-os/offline.html` while the case-sensitive
path limits the exception to the single packaged offline file. Chromium is
launched with the fully specified runtime URL.

The blocklist entries are `*` (default deny) and `view-source:*`
(prevents source viewing even when DevTools are disabled).

[url-filter-format]: https://www.chromium.org/administrators/url-blocklist-filter-format/
[url-allowlist]: https://chromeenterprise.google/policies/url-allowlist/
[url-blocklist]: https://chromeenterprise.google/policies/url-blocklist/
[devtools-policy]: https://chromeenterprise.google/policies/developer-tools-availability/

## Configurable URL

The environment file `/etc/sushida-os/config.env` contains `SUSHIDA_URL` and
`NETWORK_SETUP_GRACE_SECONDS`. Changing the URL only changes the initial URL
Chromium opens; it cannot bypass the launcher validation or the managed
policy boundary.

Only URLs within the official `https://sushida.net/` origin are permitted.
Any attempt to set `SUSHIDA_URL=http://...` or to another host is rejected
at both layers.  The launcher rejects `file:` and other non-HTTPS schemes
independently, so the policy does not need to handle them from the
config.env path.

## Local pages

### Wi-Fi setup service

The fixed `http://127.0.0.1:8787/` route is served by the unprivileged
`wifi-setup` account. It scans and connects through narrowly authorized
NetworkManager actions and atomically stores a mode-`0600` credential only on
the mounted `SUSHIDA-CFG` filesystem. Loopback IP restrictions, same-origin and
CSRF validation, request-size bounds, HTML escaping, and strict service
sandboxing prevent it from becoming a general browser or network service. If
the backend or persistent filesystem is unavailable, the launcher uses the
static offline page or refuses saving without preventing boot.

The root preparation service owns a separate `/run/sushida-config` runtime
directory for its atomic readiness marker. It does not share the
`/run/sushida-os` lifecycle: the latter is intentionally recreated with each
kiosk restart. Existing configuration entries are accepted only as real
directories with the expected ownership and private mode, never through a
symbolic link. Connection creation is serialized so boot-time credential
restoration cannot race an interactive submission.

Wi-Fi provisioning re-scans and classifies the requested SSID in the backend;
only open and WPA Personal networks are accepted. WPA2/WPA3 transition mode is
accepted as WPA Personal, while SAE-only WPA3 remains unsupported. WEP,
Enterprise/802.1X, OWE, hidden, and unknown modes are rejected before profile
changes. `nmcli connection add` creates the profile with the scanned SSID; the
SSID is not secret. WPA activation receives exactly one
`802-11-wireless-security.psk:<password>` line through the separate
`passwd-file` descriptor. Neither value is placed in process arguments or
service logs. The descriptor contexts close on every path, and the temporary
NetworkManager profile is removed after activation/configuration failure.
Saved Wi-Fi restoration uses the same path and checks the managed Wi-Fi profile
itself rather than general connectivity, allowing Ethernet and the fallback
Wi-Fi association to coexist. WPA profiles use `psk-flags=0`, so the secret is
held only by NetworkManager's volatile current-boot profile and can be used for
automatic reconnect after a link flap. The backend verifies
`connection.autoconnect=yes` and the volatile secret flag before persisting
`setup.json`; that file is the reboot recovery input, not a password-bearing
image profile.

### offline.html

The page at `file://localhost/usr/share/sushida-os/offline.html` is selected by the
launcher when NetworkManager does not report exact global connectivity. On a
later transition, the watcher validates and terminates only the managed kiosk
service MainPID; systemd restarts the whole session and the launcher selects
the newly appropriate URL. The watcher never launches a secondary browser.

The page contains only a plain-text message in Japanese explaining that
the network is unavailable.  It does not copy, imitate, or redistribute
Sushi-da content, assets, or gameplay logic.

### loading.html

The page `file:///usr/share/sushida-os/loading.html` exists in the
filesystem but is currently not used by any component.

It is intentionally excluded from the policy allowlist because:

1. No code references it in the current implementation.
2. Allowing an unused file:// URL increases the attack surface without
   demonstrated benefit.
3. If a future task introduces a loading screen, the same change must
   add the URL to the allowlist.

The launcher already rejects `file:` schemes, so loading.html cannot be
reached via config.env even if it were in the policy allowlist.

## Managed policy controls

The following managed policies are applied:

| Policy | Value | Effect |
|---|---|---|
| `DeveloperToolsAvailability` | `2` (Disallowed) | Developer tools cannot be opened |
| `BrowserGuestModeEnabled` | `false` | Guest mode disabled |
| `IncognitoModeAvailability` | `1` (Disabled) | Incognito mode disabled |
| `BrowserSignin` | `0` (Disabled) | Browser sign-in disabled |
| `PasswordManagerEnabled` | `false` | Password saving disabled |
| `AutofillAddressEnabled` | `false` | Address autofill disabled |
| `AutofillCreditCardEnabled` | `false` | Payment autofill disabled |
| `PrintingEnabled` | `false` | Printing disabled |
| `DownloadRestrictions` | `3` (Block all) | All downloads blocked |
| `URLBlocklist` | `["*", "view-source:*"]` | Default-deny navigation + view-source |
| `URLAllowlist` | 3 entries | Minimal allowed origins |

## Wi-Fi connection sequence

The POST handler that initiates a Wi-Fi connection must not execute
NetworkManager commands synchronously because an interface change aborts
any in-flight browser request, including loopback (`ERR_NETWORK_CHANGED`).
The backend therefore:

1. validates and queues the credential immediately;
2. completes the HTTP response with a transition page;
3. wakes a single serialized worker that runs the staged NetworkManager chain.

While the worker runs, the transition page polls `/status.json` through
JavaScript `fetch()`, whose failures are invisible. A terminal state
(succeeded or failed) is reported through the status endpoint; the page
either displays the outcome or reloads the interactive form.

## What managed policy alone cannot prevent

The following controls require system-level or hardware-level enforcement
beyond managed Chromium policy:

- Physical access to storage or firmware
- Booting from removable media
- Keyboard shortcut behavior that depends on compositor/browser/runtime input handling
- Physical verification of virtual-terminal switching controls
- Process inspection from another user account (kernel-level)
- DMA attacks via Thunderbolt / PCIe
- Network-level traffic interception
- Preventing a user-gesture popup or same-tab blocked navigation from
  committing an error page in Chromium (managed policy can deny navigation
  but cannot prevent the error page from replacing the current document)

These are documented in `docs/threat-model.md`.

## Verified vs. unverified

The following are verified by repository tests and image/artifact validation:

- Policy JSON is valid and contains no placeholder or duplicate keys
- Required policy names and exact configured values are checked
- URL allowlist uses explicit host (`.sushida.net`) and port (`:443`)
- Launcher and policy boundaries are consistent for the permitted origin
- `view-source:*` is added to the URLBlocklist

The following still require controlled Chromium runtime or physical hardware
verification:

- Chromium actually enforces each policy as expected
- The URL filter patterns match exactly sushida.net (not subdomains)
- Non-standard ports are blocked by the explicit `:443` in the allowlist
- `view-source:` is blocked by the policy and not circumvented by the
  allowlist
- No negative interaction between policies
- WebGL, GPU acceleration, and Chromium sandbox remain functional
- The offline page renders correctly when loaded via file://

The launcher/session BATS suite verifies Chromium argument construction and
forbidden-flag absence with stubs. It does not establish effective GPU,
sandbox, policy, audio, or kiosk-escape behavior in the real browser.
