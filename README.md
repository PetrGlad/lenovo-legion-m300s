# Lenovo Legion M300s wired mouse protocol

This repository contain captured USB data for M300s mouse.
I have collected this to add M300s support to OpenRGB, but there is also information on DPI and poll-rate settings.

TL-DR it looks like M300s uses protocol similar if not the same as Lenovo Legion M300.


# Reverse-engineering harness for the Lenovo Legion M300s (17ef:6132)

How the protocol in `PROTOCOL.md` was captured, and how to rebuild and test the
OpenRGB change. Written for Ubuntu (kernel 7.x, QEMU 10, Qt 5.15) but nothing is
distribution-specific apart from the package names.

The idea: the vendor app (Legion Accessory Central) only runs on Windows, so it runs
in a Windows 10 VM. The mouse is passed through to the VM, and the host captures all
USB traffic with `usbmon`. Wireshark is not needed inside the VM.

## 1. Host packages (needs sudo)

```
sudo apt install qemu-system-x86 qemu-utils ovmf wireshark tshark
sudo modprobe usbmon
sudo usermod -aG wireshark $USER        # then log out and back in
```

Check that KVM is available: `ls /dev/kvm`.

## 2. USB capture permissions

`/dev/usbmonN` is `root:root 0600` by default and the wireshark package does not change
that, so capturing fails with `EACCES`. Give the `wireshark` group read access:

```
echo 'SUBSYSTEM=="usbmon", GROUP="wireshark", MODE="0640"' | sudo tee /etc/udev/rules.d/85-usbmon.rules
sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=usbmon
ls -l /dev/usbmon1          # expect: crw-r----- root wireshark
```

If the rule does not take effect, this works until the next reboot:

```
sudo chgrp wireshark /dev/usbmon* && sudo chmod 640 /dev/usbmon*
```

### Which bus to capture on
The mouse's bus and device number change whenever it is re-plugged or moved to another
port. Always look it up first:

```
lsusb -d 17ef:6132
```

`Bus 001 Device 011` means capture on `usbmon1` and filter on device address 11.
In this setup the mouse was on bus 1 (port 8), and each re-plug gave a new device number
(4, 6, 7, 10, 11, ...). The bus stayed the same on that port.

### Capturing
Use `dumpcap` directly. `tshark -i usbmonN` failed with a permission error even when
`dumpcap` worked.

```
dumpcap -i usbmon1 -w capture.pcapng        # Ctrl+C to stop
```

The capture contains all devices on that bus; most of it is the mouse's movement
reports (endpoint 0x81), which can be ignored.

## 3. Windows VM

`run-vm.sh` starts QEMU with emulated SATA disk and e1000 NIC, so Windows installs without
extra drivers. Video is a 64 MB VGA with a preferred size of 1600x900 and the window
scales to fit.

Get a Windows 10 64-bit ISO from Microsoft. Activation is not needed: Windows runs
unactivated with a watermark, which does not matter here.

### Install
```
./run-vm.sh install ~/Downloads/Win10_xxx.iso
```
Boot from the CD (press a key when asked), do a custom install onto the empty 60 GB disk,
and shut Windows down from its Start menu when you reach the desktop.

The current Windows setup no longer offers an offline account when the network is up. Run
the setup with the network removed so it offers a local account:
```
NONET=1 NOMOUSE=1 ./run-vm.sh        # not "install": it would boot the ISO again
```
Choose "I don't have internet" and "Continue with limited setup". If that is not offered,
press Shift+F10 and run `oobe\bypassnro`.

### Snapshots (take them with the VM shut down)
```
qemu-img snapshot -c fresh-install win10.qcow2
qemu-img snapshot -c app-installed win10.qcow2
qemu-img snapshot -l win10.qcow2                 # list
qemu-img snapshot -a fresh-install win10.qcow2   # roll back (VM must be off)
```

### Run with the mouse
```
sudo ./run-vm.sh
```
- `sudo` is needed so QEMU can claim the USB device.
- While the VM runs the mouse is not usable on the host. Use a second mouse on the host to
  drive the VM window (QEMU's usb-tablet device gives Windows a pointer). Ctrl+Alt+G
  releases the pointer.
- The passthrough rule matches vendor/product ID, so a change of port or device number does
  not break it.
- `NOMOUSE=1` skips the passthrough, `NONET=1` removes the network.

Install Legion Accessory Central inside Windows (download from Lenovo's support site for the
M300s, over the VM's NAT network). The app should show the mouse and let you change lighting.
Without the passthrough it says "No device detected".

## 4. Capture session

1. Start the VM with `sudo ./run-vm.sh`; confirm the app sees the mouse.
2. Check the mouse's bus with `lsusb -d 17ef:6132`.
3. Start `dumpcap -i usbmonN -w captureN.pcapng` on the host.
4. In the app change ONE setting at a time and wait about 10 seconds between changes.
   Keep a written list of the exact order and values. The packets are matched to the
   settings by this list.
5. Stop the capture with Ctrl+C.

Ideas that worked: use distinctive values (for example RGB 17,29,51 or DPI 800, 1200, 2000,
3000 on slots 1..4) so the packet bytes are easy to spot. Test persistence by re-plugging the
mouse with the VM shut down, so no app can re-apply the setting.

## 5. Decoding

The control channel is USB interface 2 (vendor HID, usage page 0xFF01): host to device on
endpoint 0x04, device to host on endpoint 0x83, 64-byte packets. Filter the capture on the
mouse's device address and those two endpoints:

```
tshark -r captureN.pcapng \
  -Y 'usb.device_address==7 && (usb.endpoint_address==0x04 || usb.endpoint_address==0x83) && usb.data_len>0' \
  -T fields -e frame.time_relative -e usb.endpoint_address -e usb.capdata
```

Replace `7` with the device number. Match the timestamps against your list of actions.
The lighting packets (first byte 0x25) end with a checksum, the sum of the first 63 bytes
modulo 256; this is a quick way to confirm that a packet is read correctly.

## 6. Building and testing the OpenRGB change

```
sudo apt install git build-essential qtbase5-dev qt5-qmake qtbase5-dev-tools \
     qttools5-dev-tools libusb-1.0-0-dev libhidapi-dev pkgconf libmbedtls-dev
cd openrgb && mkdir -p build && cd build
qmake ../OpenRGB.pro && make -j$(nproc)
```

A shallow clone prints `fatal: ambiguous argument 'release_1.1..HEAD'` during `qmake`. This
is harmless: the version string is just incomplete.

### udev rules
OpenRGB needs permission to open the mouse's `hidraw` node. Generate the rules from the new
build, because rules from an older release will not list the M300s:

```
./openrgb --generate-udev-rules /tmp/60-openrgb.rules
grep -i 6132 /tmp/60-openrgb.rules          # expect a Lenovo_Legion_M300s line
sudo cp /tmp/60-openrgb.rules /etc/udev/rules.d/60-openrgb.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```
Re-plug the mouse afterwards. OpenRGB warns if the rules also exist in
`/usr/lib/udev/rules.d`; that is harmless but you can remove the older copy.

### Test (the mouse must be on the host, not in the VM)
```
./openrgb --noautoconnect --list-devices          # expect "Lenovo Legion M300s"
./openrgb --noautoconnect -d 2 -m Static -c FF0000
./openrgb --noautoconnect -d 2 -m Breathing -c FF0000,0000FF
./openrgb --noautoconnect -d 2 -m "Spectrum Cycle"
./openrgb --noautoconnect -d 2 -m Off
```
Use the device index from `--list-devices` for `-d`. The mode names are `Static`, `Off`,
`Breathing` and `Spectrum Cycle`. The mouse stores its lighting setting, so finish by
restoring the one you want to keep.

## 7. Captured data, dissector and annotations

The captures are in `pcap/`; the dissector and the script are in the project root. The
originals are never modified.

| File | Contents |
|---|---|
| `pcap/captureN.pcapng` | raw capture of the whole USB bus 1 (includes other devices and mouse movement) |
| `pcap/captureN.m300s.pcapng` | everything to and from the mouse only (still mostly movement reports) |
| `pcap/captureN.control.pcapng` | only the control channel (endpoints 0x04 / 0x83): the protocol data |
| `pcap/captureN.annotated.pcapng` | the `.control` file with packet comments linking messages to the actions performed |
| `legion_m300s.lua` | Wireshark dissector that decodes the control channel |
| `annotate_captures.py` | script that produced the annotated files (and checks each comment against the decoded message) |

Capture 2 has no control traffic (the app's changes never reached the mouse in that run).
What each capture covers: 1 = lighting modes and colours, profile add/rename/reset;
3 = Random Color, breathing with equal colours, re-plug; 4 = DPI, DPI stages, polling rate and the
DPI button.

### Viewing
```
wireshark -X lua_script:legion_m300s.lua pcap/capture4.annotated.pcapng
tshark    -X lua_script:legion_m300s.lua -r pcap/capture4.annotated.pcapng -Y m300s \
          -T fields -e frame.number -e _ws.col.info -e frame.comment
```
Or copy `legion_m300s.lua` to `~/.local/lib/wireshark/plugins/` to load it always. The comments
show in the "Packet comments" pane; filter with `frame.comment` or `frame.comment contains "DPI"`.
Other filters: `m300s.light`, `m300s.dpi`, `m300s.polling`, `m300s.button`, `m300s.slot == 2`.

Comment prefixes: `ACTION` (an action from the written action list), `NOTE` (an observation) and
`UNSURE` (matched by position only; the trigger was not recorded).

### Regenerating
```
python3 -I annotate_captures.py pcap pcap legion_m300s.lua
```
The first argument is the directory holding `captureN.control.pcapng`, the second is where the
`captureN.annotated.pcapng` files are written.
The script stops if a frame's decoded message is not what the table expects.

### Notes on the data
- Slot numbers in the dissector and in the comments are 1-based (DPI 1..4 as in the app); the
  wire value is 0-based.
- The dissector is matched by vendor/product ID when the capture contains the device
  descriptor, otherwise by endpoint (0x04 / 0x83) and report ID. None of the captures here
  contain the descriptor, because the mouse was already set up when each started.
