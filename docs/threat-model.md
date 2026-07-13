# Threat model

## In scope

- Accidental kiosk escape
- Common keyboard shortcut escape attempts
- Opening another URL
- Opening Chromium developer tools
- Starting another application
- Obtaining elevated privileges from the kiosk account
- Recovery after Chromium or Cage exits
- Recovery after sudden power loss

## Partially in scope

- Local users deliberately probing the kiosk
- Tampering that requires bootloader access

## Out of scope for software-only protection

An attacker with unrestricted physical access may remove or replace storage,
boot external media, reset firmware settings, or modify hardware.

Production deployment should therefore use a UEFI administrator password,
disable external boot, restrict case access, and prioritize the internal system
disk.
