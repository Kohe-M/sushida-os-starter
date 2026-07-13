# Architecture

## Runtime chain

```text
bootloader
  -> Debian live system
  -> systemd
  -> sushida-kiosk.service
  -> Cage
  -> Chromium kiosk window
  -> official Sushi-da URL
```

Mutable browser and session state is stored under `/run` (tmpfs).
The root filesystem is planned to be read-only in production (Task 13).

## Security boundaries

Navigation is restricted at two independent layers.

### Layer 1: Launcher (sushida-launch)

The launcher parses `/etc/sushida-os/config.env` and validates the
configured `SUSHIDA_URL` before passing it to Chromium.  Only URLs
matching the following patterns are accepted:

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
| `file:///usr/share/sushida-os/offline.html` | Local offline page (expected Task 11) |

`https://.sushida.net:443` uses the following Chromium URL filter
conventions (see [Chromium URL filter format][url-filter-format]):

- Leading dot (`.sushida.net`) — exact host match, no subdomains.
- Explicit port (`:443`) — restricts to the standard HTTPS port only.
- Omitted path component — matches any path under the origin.

The blocklist entries are `*` (default deny) and `view-source:*`
(prevents source viewing even when DevTools are disabled).

[url-filter-format]: https://www.chromium.org/administrators/url-blocklist-filter-format/
[url-allowlist]: https://chromeenterprise.google/policies/url-allowlist/
[url-blocklist]: https://chromeenterprise.google/policies/url-blocklist/
[devtools-policy]: https://chromeenterprise.google/policies/developer-tools-availability/

## Configurable URL

The environment file `/etc/sushida-os/config.env` contains a single
`SUSHIDA_URL` variable.  Changing this value only changes the initial URL
Chromium opens; it cannot bypass the launcher validation or the managed
policy boundary.

Only URLs within the official `https://sushida.net/` origin are permitted.
Any attempt to set `SUSHIDA_URL=http://...` or to another host is rejected
at both layers.  The launcher rejects `file:` and other non-HTTPS schemes
independently, so the policy does not need to handle them from the
config.env path.

## Local pages

### offline.html

The page at `file:///usr/share/sushida-os/offline.html` is intended for
display by the network watcher (Task 11) when connectivity is lost.
It is allowed in the managed policy pre-emptively because the offline
flow will require it.

The network watcher is currently a placeholder; the page is not yet
displayed at runtime.

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
| `URLAllowlist` | 2 entries | Minimal allowed origins |

## What managed policy alone cannot prevent

The following controls require system-level or hardware-level enforcement
beyond managed Chromium policy:

- Physical access to storage or firmware
- Booting from removable media
- Keyboard shortcut interception (Alt+Tab, Ctrl+Alt+T, etc. — Task 9)
- Virtual terminal switching (Task 9)
- Process inspection from another user account (kernel-level)
- DMA attacks via Thunderbolt / PCIe
- Network-level traffic interception

These are documented in `docs/threat-model.md`.

## Verified vs. unverified

The following were confirmed by static inspection of this repository:

- Policy JSON is valid and contains no placeholder or duplicate keys
- All required policy names match those expected by Chromium enterprise
  policy documentation
- URL allowlist uses explicit host (`.sushida.net`) and port (`:443`)
- Launcher and policy boundaries are consistent for the permitted origin
- `view-source:*` is added to the URLBlocklist

The following require QEMU, real hardware, or a Debian 13 Chromium runtime
to verify:

- Chromium actually enforces each policy as expected
- The URL filter patterns match exactly sushida.net (not subdomains)
- Non-standard ports are blocked by the explicit `:443` in the allowlist
- `view-source:` is blocked by the policy and not circumvented by the
  allowlist
- No negative interaction between policies
- WebGL, GPU acceleration, and Chromium sandbox remain functional
- The offline page renders correctly when loaded via file://

Policy values were selected based on Chromium enterprise policy
documentation.  Runtime verification with Debian 13 Chromium has not been
performed.
