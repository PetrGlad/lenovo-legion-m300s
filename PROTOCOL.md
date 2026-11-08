# Lenovo Legion M300s RGB (17ef:6132) – lighting protocol notes

Source: usbmon capture of Legion Accessory Central (Win10 VM), capture1.pcapng.

## Transport
- USB interface 2, vendor HID, usage page 0xFF01, no report ID.
- OUT: interrupt endpoint 0x04, 64 bytes. IN: interrupt endpoint 0x83, 64 bytes.
- hidapi: write 65 bytes (leading 0x00 report id), read 64 bytes.
- Interfaces 0 (mouse) and 1 (keyboard) are normal HID and must not be touched.

## Lighting command (report 0x25)
```
b0  0x25            command
b1  0x00            (host->dev); device replies with b1=0x01
b2  0x01
b3  0x01
b4  0x0c            payload length (12)
b5  mode            0x03 static, 0x02 breathing, 0x01 rainbow/cycle
b6  brightness      0x64 (100) in all captures; 0x00 together with static black = "Off"
b7  0x00            0x01 = "Random Colour" (static mode, RGB 0); 0x00 otherwise
b8.. mode data      (see below)
b63 checksum        sum(b0..b62) & 0xFF   -- verified on all packets
```
Device replies with `25 01 01 01 00 ...` (ack).

### Mode data (from b8) -- all verified against captures
- static (0x03):   b7=0x00, `R G B` at b8..b10
- random colour (0x03): same static packet with b7=0x01 and RGB = 0 (confirmed)
- off: static, brightness b6=0x00, RGB 0
- breathing (0x02): `02 <flags> 00 R1 G1 B1 R2 G2 B2` starting at b8
    - flags = 0x01 with default/one colour, 0x03 once both colours are set
    - the mouse alternates colour1, colour2 each cycle; to get a single colour
      send the same colour twice (red,red = `02 03 00 ff 00 00 ff 00 00`)
    - no colours set = black (`02 01 00 00 00 00 ...`)
- rainbow (0x01):  `0a` at b8 (fixed; the app exposes no speed control)

The app has no brightness or speed controls, so brightness stays 0x64 and
speed bytes are fixed.

## Persistence
The setting survives unplug/replug with no app running -> stored in mouse flash.
Each 0x25 command is acked on EP 0x83 with `25 01 01 01 00 ...`.

## DPI and polling rate (report 0x04) -- decoded from capture4, no checksum
All packets are 64 bytes on the same endpoints. Host packets are `04 <op> <b2> <b3> ...`;
the device acks with the same packet with b2 changed to 0x01 where noted.

| purpose | host -> device | ack |
|---|---|---|
| set DPI of slot | `04 01 00 <slot> <v lo> <v hi> <v lo> <v hi>` | `04 01 01 <slot> <same value>` |
| set number of DPI stages | `04 01 02 <N-1>` | (none seen) |
| set active DPI slot (sent by app before lowering the stage count) | `04 01 01 <slot>` | (none seen) |
| set polling rate | `04 02 00 <code>` | `04 02 01 <code>` |

- slot = 0..3. DPI value = DPI / 100 as 16-bit little endian, written twice (X, Y;
  the app has a single value). Range 200..8000 DPI in steps of 100 (0x02..0x50).
  Verified: 800=0x08, 1200=0x0c, 2000=0x14, 3000=0x1e, 8000=0x50.
- Stage count: the app allows 1..4; `<N-1>` = 0..3 (4 stages = `04 01 02 03`).
- Polling code: 125 Hz=0x08, 250 Hz=0x04, 500 Hz=0x02, 1000 Hz=0x00.
- Factory DPI table (from profile dump): 400, 800, 1600, 2400 (`04 00 04 00 08 00 08 00 10 00 10 00 18 00 18 00`).

### Unsolicited notification: physical DPI button
Device -> host: `04 00 00 <slot> <v lo> 00 ...` = newly active slot and its value
(value byte is the DPI/100 of that slot). With N stages the button cycles
slot 0 -> 1 -> ... -> N-1 -> 0 (verified for N = 1..4).

## Other traffic (profile storage, not needed for lighting)
- Report 0x01 (cmd 03 3a ...) writes profile blocks incl. UTF-8 profile name.
- `05 00 ..` / `07 05 ..` / `03 ff ..` : commit / read-back of full profile dump.

## Still unknown
- exact meaning of `04 01 01 <slot>` (inferred: select active slot; always seen just before
  lowering the stage count) and the `01 64 00 01` bytes in the profile dump.
- whether the polling rate is flash-persistent (lighting and DPI are: both survived a re-plug).
- number of independent zones (only one colour seen; app shows one).
