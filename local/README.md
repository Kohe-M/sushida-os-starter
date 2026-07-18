# Local configuration

This directory is for machine-local or secret deployment settings.

Real files in this directory are ignored by Git except for documented examples.

## Wi-Fi

Copy the example and replace the credentials:

```bash
cp local/wifi.nmconnection.example local/wifi.nmconnection
chmod 600 local/wifi.nmconnection
```

Then replace the example SSID and password.

When this file exists during `make configure`, it is automatically staged
into the build tree with mode `0600`.  Without the file, the image is built
without any Wi-Fi profile (wired Ethernet only).

Any credentials embedded in an ISO can be extracted by a person who obtains
that ISO.  Use a dedicated network credential where possible.

To update build-time Wi-Fi credentials, replace `local/wifi.nmconnection` and
rebuild the ISO. Production images also include a fixed loopback-only
provisioning page for entering a personal Wi-Fi credential when no connection
is available. It is not a general NetworkManager settings GUI and exposes no
files, commands, arbitrary URLs, or shell.
