#!/usr/bin/env bash
# Usage:
#   ./run-vm.sh install /path/to/Win10.iso   # first boot: install Windows
#   ./run-vm.sh                              # later boots (mouse passed through)
set -euo pipefail
cd "$(dirname "$0")"

DISK=win10.qcow2
[ -f "$DISK" ] || qemu-img create -f qcow2 "$DISK" 60G

# NONET=1 ./run-vm.sh ...  -> no network (forces local account during Windows setup)
if [ -n "${NONET:-}" ]; then NIC=none; else NIC=user,model=e1000; fi

ARGS=(
  -enable-kvm -cpu host -smp 4 -m 6G
  -machine q35
  -device VGA,vgamem_mb=64,xres=1600,yres=900 -display gtk,zoom-to-fit=on
  -drive file="$DISK",if=none,id=hd0,format=qcow2
  -device ich9-ahci,id=ahci -device ide-hd,drive=hd0,bus=ahci.0
  -nic "$NIC"
  -device qemu-xhci,id=xhci
  -device usb-tablet,bus=xhci.0
  -rtc base=localtime
)

if [ "${1:-}" = install ]; then
  ARGS+=(-cdrom "$2" -boot d)
elif [ -z "${NOMOUSE:-}" ]; then
  # Pass the Legion mouse through to the guest (needs access to /dev/bus/usb -> run with sudo)
  ARGS+=(-device usb-host,bus=xhci.0,vendorid=0x17ef,productid=0x6132)
fi

exec qemu-system-x86_64 "${ARGS[@]}"
