-- Wireshark dissector for the Lenovo Legion M300s RGB Gaming Mouse (USB 17ef:6132)
--
-- Decodes the vendor control channel (USB interface 2, endpoints 0x04 OUT / 0x83 IN,
-- 64-byte reports). Protocol details: PROTOCOL.md.
--
-- Usage:
--   tshark   -X lua_script:legion_m300s.lua -r capture4.control.pcapng
--   wireshark -X lua_script:legion_m300s.lua capture4.control.pcapng
-- or copy this file to ~/.local/lib/wireshark/plugins/ to load it automatically.
--
-- Useful display filters:  m300s   m300s.light   m300s.dpi   m300s.polling   m300s.button
--
-- SPDX-License-Identifier: GPL-2.0-or-later

local m300s = Proto("m300s", "Lenovo Legion M300s control channel")

local VID_PID = 0x17ef6132

local f = m300s.fields
f.kind      = ProtoField.string("m300s.kind",       "Message kind")
f.report    = ProtoField.uint8 ("m300s.report",     "Report ID", base.HEX)
f.summary   = ProtoField.string("m300s.summary",    "Summary")
f.mode      = ProtoField.uint8 ("m300s.mode",       "Lighting mode", base.HEX)
f.bright    = ProtoField.uint8 ("m300s.brightness", "Brightness", base.DEC)
f.random    = ProtoField.bool  ("m300s.random",     "Random colour flag")
f.rgb1      = ProtoField.string("m300s.rgb1",       "Colour 1 (RGB)")
f.rgb2      = ProtoField.string("m300s.rgb2",       "Colour 2 (RGB)")
f.csum      = ProtoField.uint8 ("m300s.checksum",   "Checksum", base.HEX)
f.csum_ok   = ProtoField.bool  ("m300s.checksum_ok","Checksum valid")
f.slot      = ProtoField.uint8 ("m300s.slot",       "DPI slot (0-based)", base.DEC)
f.dpi       = ProtoField.uint16("m300s.dpi",        "DPI", base.DEC)
f.stages    = ProtoField.uint8 ("m300s.stages",     "Number of DPI stages", base.DEC)
f.polling   = ProtoField.uint16("m300s.polling",    "Polling rate (Hz)", base.DEC)
f.raw       = ProtoField.bytes ("m300s.raw",        "Raw report")

local f_endpoint = Field.new("usb.endpoint_address")

local MODE_NAMES = { [0x01] = "rainbow", [0x02] = "breathing", [0x03] = "static" }
local POLL_HZ    = { [0x08] = 125, [0x04] = 250, [0x02] = 500, [0x00] = 1000 }

local function rgb(b, o)
    return string.format("%d,%d,%d", b(o, 1):uint(), b(o + 1, 1):uint(), b(o + 2, 1):uint())
end

-- Returns summary, kind and a table of extra fields to add
local function decode(buf, is_in)
    local rpt = buf(0, 1):uint()
    local x = {}

    ------------------------------------------------------------------
    -- Report 0x25: lighting (checksum = sum of bytes 0..62 modulo 256)
    ------------------------------------------------------------------
    if rpt == 0x25 then
        if is_in then
            return "Lighting: acknowledged", "light-ack", x
        end
        local mode, bri, flag = buf(5, 1):uint(), buf(6, 1):uint(), buf(7, 1):uint()
        x.mode, x.bright = buf(5, 1), buf(6, 1)
        local sum = 0
        for i = 0, 62 do sum = sum + buf(i, 1):uint() end
        x.csum_val, x.csum_ok = buf(63, 1), (sum % 256) == buf(63, 1):uint()
        local s
        if mode == 0x03 then
            if flag == 0x01 then
                x.random = buf(7, 1)
                s = "Lighting: random colour"
            elseif bri == 0 then
                s = "Lighting: off (static, brightness 0)"
            else
                x.rgb1 = rgb(buf, 8)
                s = "Lighting: static RGB " .. x.rgb1
            end
        elseif mode == 0x02 then
            x.rgb1, x.rgb2 = rgb(buf, 11), rgb(buf, 14)
            s = string.format("Lighting: breathing %s <-> %s", x.rgb1, x.rgb2)
        elseif mode == 0x01 then
            s = "Lighting: rainbow / spectrum cycle"
        else
            s = string.format("Lighting: unknown mode 0x%02X", mode)
        end
        if not x.csum_ok then s = s .. " [BAD CHECKSUM]" end
        return s, "light", x
    end

    ------------------------------------------------------------------
    -- Report 0x04: DPI, DPI stages, polling rate, DPI button
    ------------------------------------------------------------------
    if rpt == 0x04 then
        local op, b2, b3 = buf(1, 1):uint(), buf(2, 1):uint(), buf(3, 1):uint()
        if is_in and op == 0x00 then
            x.slot = buf(3, 1); x.dpi = buf(4, 1)
            return string.format("DPI button pressed: slot %d active (%d DPI)", b3 + 1, buf(4, 1):uint() * 100),
                   "button", x
        elseif op == 0x01 then
            if b2 == 0x00 and not is_in then
                x.slot = buf(3, 1); x.dpi = buf(4, 2)
                return string.format("DPI: set slot %d = %d DPI", b3 + 1, buf(4, 2):le_uint() * 100), "dpi", x
            elseif b2 == 0x01 and is_in then
                x.slot = buf(3, 1); x.dpi = buf(4, 2)
                return string.format("DPI: acknowledged slot %d = %d DPI", b3 + 1, buf(4, 2):le_uint() * 100),
                       "dpi-ack", x
            elseif b2 == 0x02 and not is_in then
                x.stages = buf(3, 1)
                return string.format("DPI: set number of stages = %d", b3 + 1), "stages", x
            elseif b2 == 0x01 and not is_in then
                x.slot = buf(3, 1)
                return string.format("DPI: select slot %d (inferred)", b3 + 1), "select-slot", x
            end
        elseif op == 0x02 then
            local hz = POLL_HZ[b3]
            if hz then x.polling = hz end
            local txt = hz and (hz .. " Hz") or string.format("code 0x%02X", b3)
            if is_in and b2 == 0x01 then
                return "Polling rate: acknowledged " .. txt, "polling-ack", x
            elseif not is_in and b2 == 0x00 then
                return "Polling rate: set " .. txt, "polling", x
            end
        end
        return string.format("Report 0x04: unrecognised (%02X %02X %02X)", op, b2, b3), "unknown", x
    end

    ------------------------------------------------------------------
    -- Profile storage / commit traffic (not decoded)
    ------------------------------------------------------------------
    if rpt == 0x01 or rpt == 0x03 or rpt == 0x05 or rpt == 0x07 then
        return string.format("Profile storage / commit (report 0x%02X, not decoded)", rpt), "profile", x
    end

    return string.format("Unknown report 0x%02X", rpt), "unknown", x
end

local KNOWN_REPORTS = { [0x01] = true, [0x03] = true, [0x04] = true, [0x05] = true,
                        [0x07] = true, [0x25] = true }

function m300s.dissector(tvb, pinfo, tree)
    if tvb:len() ~= 64 then return 0 end

    local ep = f_endpoint()
    local is_in = ep ~= nil and ep.value >= 0x80

    -- Captures often lack the device descriptor, so the product cannot be matched and
    -- this dissector is also tried for every unknown-class interrupt transfer. Only
    -- accept the control channel's endpoints (0x04 OUT / 0x83 IN) and known reports.
    if ep == nil or (ep.value ~= 0x04 and ep.value ~= 0x83) then return 0 end
    if not KNOWN_REPORTS[tvb(0, 1):uint()] then return 0 end
    local summary, kind, x = decode(tvb, is_in)

    pinfo.cols.protocol = "M300s"
    pinfo.cols.info = summary

    local t = tree:add(m300s, tvb(), "Legion M300s: " .. summary)
    t:add(f.kind, kind):set_generated()
    t:add(f.report, tvb(0, 1))
    t:add(f.summary, summary):set_generated()
    if x.mode    then t:add(f.mode, x.mode) end
    if x.bright  then t:add(f.bright, x.bright) end
    if x.random  then t:add(f.random, x.random) end
    if x.rgb1    then t:add(f.rgb1, x.rgb1):set_generated() end
    if x.rgb2    then t:add(f.rgb2, x.rgb2):set_generated() end
    if x.csum_val then
        t:add(f.csum, x.csum_val)
        t:add(f.csum_ok, x.csum_ok):set_generated()
    end
    if x.slot    then t:add(f.slot, x.slot) end
    if x.dpi     then t:add(f.dpi, x.dpi) end
    if x.stages  then t:add(f.stages, x.stages) end
    if x.polling then t:add(f.polling, x.polling):set_generated() end
    t:add(f.raw, tvb())
    return tvb:len()
end

-- Matched by vendor/product ID when the capture includes the device descriptor ...
DissectorTable.get("usb.product"):add(VID_PID, m300s)
-- ... and by endpoint/report checks (above) when it does not.
DissectorTable.get("usb.interrupt"):add(0xFFFF, m300s)
