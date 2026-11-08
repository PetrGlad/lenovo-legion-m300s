#!/usr/bin/env python3
"""Add packet comments to the Legion M300s control-channel captures.

Each comment links a message to the action that was performed in Legion Accessory Central
(or on the mouse itself) at that moment. The actions come from the written lists kept while
capturing, matched to the messages by order and content.

Every entry is checked against the dissector output before it is written: if the decoded
message at that frame number does not contain the expected text, the script stops.

Usage:
    python3 -I annotate_captures.py <dir with captureN.control.pcapng> <output dir> <dissector.lua>

Input files:  captureN.control.pcapng  (N = 1, 3, 4)
Output files: captureN.annotated.pcapng
View in Wireshark (comments are in the "Packet comments" pane; filter: frame.comment):
    wireshark -X lua_script:legion_m300s.lua captureN.annotated.pcapng

Comment prefixes:
    ACTION  an action from the written action list, matched to this message
    NOTE    an observation about the message (not an action in the list)
    UNSURE  matched by position/timing only, the exact trigger was not recorded
"""
import subprocess
import sys

# frame number -> (text the decoded message must contain, comment)
# Frame numbers refer to the *.control.pcapng files.
C1 = {
    1:   ("off", "ACTION: Off selected"),
    5:   ("static RGB 0,255,0", "ACTION: Static selected (the app sent its default colour, green, first)"),
    9:   ("static RGB 255,0,0", "ACTION: colour picked: red"),
    13:  ("static RGB 71,41,15", "ACTION: colour picked: 71,41,15"),
    17:  ("static RGB 17,29,51", "ACTION: colour picked: 17,29,51"),
    21:  ("off", "UNSURE: Off sent again; not in the action list (the app was probably toggled quickly)"),
    25:  ("static RGB 17,29,51", "UNSURE: static 17,29,51 re-applied right after the Off above; not in the action list"),
    29:  ("breathing 0,0,0 <-> 0,0,0", "ACTION: Breathing selected, default colours (both black)"),
    33:  ("breathing 0,158,255 <-> 0,0,0", "ACTION: Breathing, colour 1 set to blue (0,158,255); colour 2 left unset"),
    37:  ("breathing 0,158,255 <-> 0,255,0", "ACTION: Breathing, colour 2 set to green (0,255,0)"),
    41:  ("rainbow", "ACTION: Rainbow selected"),
    45:  ("random colour", "ACTION: Random Color selected"),
    49:  ("report 0x01", "UNSURE: profile write (3 packets + commit): belongs to the add profile / rename / switch profile steps; the individual steps cannot be told apart"),
    61:  ("report 0x05", "NOTE: commit of the profile write above"),
    65:  ("static RGB 17,29,51", "ACTION: Static selected on 'Second profile' (colour carried over)"),
    69:  ("static RGB 0,99,187", "ACTION: Static colour picked: blue"),
    73:  ("static RGB 102,0,0", "ACTION: Static colour picked: dark red"),
    77:  ("report 0x07", "ACTION: 'Reset mouse to defaults' (profile reset commands follow)"),
    85:  ("report 0x03", "NOTE: the app reads the full profile back; the replies carry the default profile (two profile names, DPI table 400/800/1600/2400)"),
}

C3 = {
    1:   ("static RGB 255,0,0", "ACTION: Static red"),
    5:   ("random colour", "ACTION: Random Color (static mode with the random flag set)"),
    9:   ("breathing 255,0,0 <-> 0,0,255", "ACTION: Breathing, red + blue (the app remembered earlier settings, so both colours went out together)"),
    13:  ("report 0x03", "NOTE: the app reads the full profile back; the trigger was not recorded"),
    25:  ("breathing 255,0,0 <-> 255,0,0", "ACTION: Breathing, red + red (same colour twice = no alternation)"),
    29:  ("static RGB 255,0,0", "ACTION: Static red"),
    35:  ("report 0x03", "UNSURE: profile read after the mouse was re-plugged while the VM was running"),
}

C4 = {
    1:   ("DPI button pressed", "ACTION: physical DPI button pressed (the mouse reports the newly active slot)"),
    3:   ("DPI button pressed", "ACTION: physical DPI button pressed"),
    5:   ("DPI button pressed", "ACTION: physical DPI button pressed"),
    7:   ("DPI button pressed", "ACTION: physical DPI button pressed"),
    9:   ("set slot 1 = 200 DPI", "ACTION: DPI 1 slider dragged to the minimum (200)"),
    13:  ("set slot 1 = 1000 DPI", "NOTE: DPI 1 slider drag; every step is a separate message"),
    77:  ("set slot 1 = 8000 DPI", "ACTION: DPI 1 slider dragged to the maximum (8000)"),
    93:  ("set slot 1 = 200 DPI", "ACTION: DPI 1 slider back to the minimum (200)"),
    97:  ("set slot 1 = 8000 DPI", "ACTION: DPI 1 slider to the maximum (8000) again"),
    113: ("set slot 1 = 200 DPI", "ACTION: DPI 1 slider to the minimum (200) again"),
    117: ("set slot 1 = 8000 DPI", "ACTION: DPI 1 slider to the maximum (8000) again"),
    121: ("set slot 1 = 800 DPI", "ACTION: DPI1 := 800 (first of the 16 planned changes)"),
    125: ("set slot 3 = 800 DPI", "ACTION: DPI3 := 800. NOTE: DPI2 := 800 sent no message, slot 2 was already 800"),
    129: ("set slot 4 = 900 DPI", "NOTE: DPI4 slider overshoot (900) on the way to 800"),
    133: ("set slot 4 = 800 DPI", "ACTION: DPI4 := 800"),
    137: ("set slot 1 = 1200 DPI", "ACTION: DPI1 := 1200"),
    141: ("set slot 2 = 1200 DPI", "ACTION: DPI2 := 1200"),
    145: ("set slot 3 = 1200 DPI", "ACTION: DPI3 := 1200"),
    149: ("set slot 4 = 1200 DPI", "ACTION: DPI4 := 1200"),
    153: ("set slot 1 = 2000 DPI", "ACTION: DPI1 := 2000"),
    157: ("set slot 2 = 2000 DPI", "ACTION: DPI2 := 2000"),
    161: ("set slot 3 = 2000 DPI", "ACTION: DPI3 := 2000"),
    165: ("set slot 4 = 2100 DPI", "NOTE: DPI4 slider overshoot (2100) on the way to 2000"),
    169: ("set slot 4 = 2000 DPI", "ACTION: DPI4 := 2000"),
    173: ("set slot 1 = 3000 DPI", "ACTION: DPI1 := 3000"),
    177: ("set slot 2 = 3000 DPI", "ACTION: DPI2 := 3000"),
    181: ("set slot 3 = 3000 DPI", "ACTION: DPI3 := 3000"),
    185: ("set slot 4 = 3000 DPI", "ACTION: DPI4 := 3000"),
    189: ("slot 3 active", "ACTION: physical DPI button pressed (first of two presses, slot 2 -> 3)"),
    191: ("slot 4 active", "ACTION: physical DPI button pressed (second press, slot 3 -> 4)"),
    193: ("select slot 3", "NOTE: sent just before lowering the stage count (meaning inferred: select active slot)"),
    197: ("stages = 3", "ACTION: number of stages lowered 4 -> 3"),
    205: ("stages = 2", "ACTION: number of stages lowered 3 -> 2"),
    213: ("stages = 1", "ACTION: number of stages lowered 2 -> 1"),
    217: ("stages = 2", "ACTION: number of stages raised 1 -> 2"),
    221: ("stages = 3", "ACTION: number of stages raised 2 -> 3"),
    225: ("stages = 4", "ACTION: number of stages raised 3 -> 4 (the allowed maximum)"),
    229: ("stages = 3", "ACTION: number of stages lowered 4 -> 3 (reset to 1 stage, step 1)"),
    233: ("stages = 2", "ACTION: number of stages lowered 3 -> 2 (reset to 1 stage, step 2)"),
    237: ("stages = 1", "ACTION: number of stages lowered 2 -> 1 (reset to 1 stage, step 3)"),
    241: ("slot 1 active", "ACTION: DPI button pressed with 1 stage (stays on slot 1)"),
    243: ("slot 1 active", "UNSURE: second notification with 1 stage, still slot 1 (one press was reported)"),
    245: ("stages = 2", "ACTION: number of stages raised to 2"),
    249: ("slot 2 active", "ACTION: DPI button press 1 of 2 (2 stages)"),
    251: ("slot 1 active", "ACTION: DPI button press 2 of 2 (2 stages, wraps to slot 1)"),
    253: ("stages = 3", "ACTION: number of stages raised to 3"),
    257: ("slot 2 active", "ACTION: DPI button press 1 of 3 (3 stages)"),
    259: ("slot 3 active", "ACTION: DPI button press 2 of 3"),
    261: ("slot 1 active", "ACTION: DPI button press 3 of 3 (wraps to slot 1)"),
    263: ("stages = 4", "ACTION: number of stages raised to 4"),
    267: ("slot 2 active", "ACTION: DPI button press 1 of 4 (4 stages)"),
    269: ("slot 3 active", "ACTION: DPI button press 2 of 4"),
    271: ("slot 4 active", "ACTION: DPI button press 3 of 4"),
    273: ("slot 1 active", "ACTION: DPI button press 4 of 4 (wraps to slot 1)"),
    275: ("set 125 Hz", "ACTION: polling rate set to 125 Hz"),
    279: ("set 250 Hz", "ACTION: polling rate set to 250 Hz"),
    283: ("set 500 Hz", "ACTION: polling rate set to 500 Hz"),
    287: ("set 1000 Hz", "ACTION: polling rate set to 1000 Hz"),
}

# Slider drag steps that are annotated as a group (frames of DPI 1 slider drags)
for fr in (17, 21, 25, 29, 33, 37, 41, 45, 49, 53, 57, 61, 65, 69, 73, 81, 85, 89,
           101, 105, 109):
    C4.setdefault(fr, (None, "NOTE: DPI 1 slider drag step"))

JOBS = {1: C1, 3: C3, 4: C4}


def info_by_frame(path, lua):
    out = subprocess.check_output(
        ["tshark", "-X", "lua_script:" + lua, "-r", path, "-Y", "m300s",
         "-T", "fields", "-e", "frame.number", "-e", "_ws.col.info"], text=True)
    res = {}
    for line in out.splitlines():
        num, _, text = line.partition("\t")
        res[int(num)] = text
    return res


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    indir, outdir, lua = sys.argv[1:4]
    for n, table in JOBS.items():
        src = f"{indir}/capture{n}.control.pcapng"
        dst = f"{outdir}/capture{n}.annotated.pcapng"
        info = info_by_frame(src, lua)
        args = []
        for frame in sorted(table):
            expect, comment = table[frame]
            got = info.get(frame)
            if got is None or (expect is not None and expect not in got):
                sys.exit(f"capture{n} frame {frame}: expected '{expect}', found '{got}'")
            args += ["-a", f"{frame}:{comment}"]
        subprocess.check_call(["editcap", "--discard-packet-comments", *args, src, dst])
        print(f"capture{n}: {len(table)} comments -> {dst}")


if __name__ == "__main__":
    main()
