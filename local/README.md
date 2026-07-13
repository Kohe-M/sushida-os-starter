# Local configuration

This directory is for machine-local or secret deployment settings.

Real files in this directory are ignored by Git except for documented examples.

## Wi-Fi

Copy:

```bash
cp local/wifi.nmconnection.example local/wifi.nmconnection
chmod 600 local/wifi.nmconnection
```

Then replace the example SSID and password.

Any credentials embedded in an ISO can be extracted by a person who obtains
that ISO. Use a dedicated network credential where possible.
