--[[
    ARCADE ASSISTANT LIVE SCORE BROADCASTER
    =========================================
    Reads game scores from RAM and writes to mame_scores.json
    for ScoreKeeper Sam to consume.
    
    Governance:
    - READ-ONLY on RAM (no writes)
    - Writes JSON to sanctioned path: A:/.aa/state/scorekeeper/
    - Uses split-digit logic for BCD-encoded scores
    
    Supported Games:
    - galaga (0x83F8-0x83FD, 6 BCD digits)
    - dkong (0x6020-0x6025, 6 BCD digits)
    - pacman (0x4E80-0x4E85, 6 BCD digits)
    - mspacman (0x4E80-0x4E85, 6 BCD digits)
]]

local exports = {}
exports.name = "arcade_assistant_scores"
exports.version = "1.0"
exports.description = "Arcade Assistant Live Score Broadcaster"
exports.license = "MIT"
exports.author = { name = "Arcade Assistant" }

-- Configuration
local OUTPUT_PATH = "A:/.aa/state/scorekeeper/mame_scores.json"
local POLL_INTERVAL = 0.5  -- seconds between score reads
local DEBUG = false

-- Game-specific score memory maps
-- Format: { start_addr, num_digits, multiplier_per_digit }
local SCORE_MAPS = {
    -- Galaga: 6 BCD digits at 0x83F8-0x83FD
    galaga = {
        p1_addr = 0x83F8,
        digits = 6,
        type = "bcd_split"  -- Each byte is one digit (0-9)
    },
    galagao = {
        p1_addr = 0x83F8,
        digits = 6,
        type = "bcd_split"
    },
    gallag = {
        p1_addr = 0x83F8,
        digits = 6,
        type = "bcd_split"
    },
    
    -- Donkey Kong: 6 BCD digits at 0x6020-0x6025
    dkong = {
        p1_addr = 0x6020,
        digits = 6,
        type = "bcd_split"
    },
    dkongjr = {
        p1_addr = 0x6020,
        digits = 6,
        type = "bcd_split"
    },
    
    -- Pac-Man: 6 BCD digits at 0x4E80-0x4E85
    pacman = {
        p1_addr = 0x4E80,
        digits = 6,
        type = "bcd_split"
    },
    mspacman = {
        p1_addr = 0x4E80,
        digits = 6,
        type = "bcd_split"
    },
    
    -- Space Invaders: 2 bytes at 0x20F1-0x20F2 (16-bit binary)
    invaders = {
        p1_addr = 0x20F1,
        digits = 2,
        type = "binary_16"
    },
    
    -- Donkey Kong 3: 6 BCD digits
    dkong3 = {
        p1_addr = 0x6100,
        digits = 6,
        type = "bcd_split"
    }
}

-- State tracking
local current_rom = nil
local last_score = 0
local last_write_time = 0
local cpu = nil
local mem = nil

-- Helper: Read BCD split digits (each byte = one digit 0-9)
local function read_bcd_split(start_addr, num_digits)
    local score = 0
    local multiplier = 1
    
    -- Read from least significant to most significant
    for i = num_digits - 1, 0, -1 do
        local digit = mem:read_u8(start_addr + i)
        -- Clamp to 0-9 (safety)
        if digit > 9 then digit = 0 end
        score = score + (digit * multiplier)
        multiplier = multiplier * 10
    end
    
    return score
end

-- Helper: Read 16-bit binary score (little-endian)
local function read_binary_16(addr)
    local lo = mem:read_u8(addr)
    local hi = mem:read_u8(addr + 1)
    return (hi * 256) + lo
end

-- Read score for current game
local function read_current_score()
    if not current_rom or not SCORE_MAPS[current_rom] then
        return nil
    end
    
    local map = SCORE_MAPS[current_rom]
    
    if map.type == "bcd_split" then
        return read_bcd_split(map.p1_addr, map.digits)
    elseif map.type == "binary_16" then
        return read_binary_16(map.p1_addr)
    end
    
    return nil
end

-- Write score to JSON file (MERGE with existing data)
local function write_score_json(score)
    local timestamp = os.date("!%Y-%m-%dT%H:%M:%SZ")
    
    -- Read existing scores first (to merge, not overwrite)
    local existing_data = {}
    local file = io.open(OUTPUT_PATH, "r")
    if file then
        local content = file:read("*all")
        file:close()
        
        -- Simple JSON parsing for our known format
        -- The format is: { "romname": [ {score entries} ], ... }
        if content and content ~= "" then
            -- Try to load existing data
            -- Lua doesn't have native JSON, so we use a simple approach
            -- For now, we'll rebuild the file with merged data
            existing_data = {}
            for rom_match in content:gmatch('"([%w_]+)"%s*:%s*%[') do
                existing_data[rom_match] = true  -- Mark as existing
            end
        end
    end
    
    -- Create the entry for this game
    local entry = string.format([[{
      "rank": 1,
      "score": %d,
      "name": "LIVE",
      "rom": "%s",
      "game_name": "%s",
      "timestamp": "%s",
      "source": "arcade_assistant_scores"
    }]], score, current_rom, current_rom, timestamp)
    
    -- Build the merged output
    -- We'll write just this game's entry - the hi2txt watcher will handle the rest
    -- This uses a separate "live scores" file to avoid conflicts
    local live_path = OUTPUT_PATH:gsub("mame_scores.json", "mame_live_score.json")
    
    local live_json = string.format([[{
  "rom": "%s",
  "score": %d,
  "player": 1,
  "name": "LIVE",
  "timestamp": "%s",
  "source": "arcade_assistant_scores",
  "version": "1.0"
}]], current_rom, score, timestamp)
    
    -- Write to separate live file (won't conflict with hi2txt)
    local live_file = io.open(live_path, "w")
    if live_file then
        live_file:write(live_json)
        live_file:close()
        if DEBUG then
            print(string.format("[AA Scores] Wrote live score %d for %s to mame_live_score.json", score, current_rom))
        end
        return true
    else
        print("[AA Scores] ERROR: Could not write to " .. live_path)
        return false
    end
end

-- Plugin callbacks
function exports.startplugin()
    print("[AA Scores] Arcade Assistant Score Broadcaster v1.0 starting...")
    
    -- Get ROM name
    local machine = manager.machine
    if not machine then
        print("[AA Scores] No machine available")
        return
    end
    
    current_rom = emu.romname()
    print("[AA Scores] ROM: " .. (current_rom or "unknown"))
    
    -- Check if we support this game
    if not SCORE_MAPS[current_rom] then
        print("[AA Scores] No score map for " .. (current_rom or "unknown") .. ", plugin inactive")
        return
    end
    
    print("[AA Scores] Score tracking active for " .. current_rom)
    
    -- Get CPU and memory
    local devices = machine.devices
    for tag, device in pairs(devices) do
        if device.spaces and device.spaces["program"] then
            cpu = device
            mem = device.spaces["program"]
            print("[AA Scores] Found CPU: " .. tag)
            break
        end
    end
    
    if not mem then
        print("[AA Scores] ERROR: Could not find program memory space")
        return
    end
    
    -- Register frame callback
    emu.register_frame_done(function()
        -- Rate limit to POLL_INTERVAL
        local now = os.clock()
        if now - last_write_time < POLL_INTERVAL then
            return
        end
        
        -- Read current score
        local score = read_current_score()
        if score and score ~= last_score and score > 0 then
            last_score = score
            last_write_time = now
            write_score_json(score)
        end
    end)
    
    print("[AA Scores] Frame callback registered, polling every " .. POLL_INTERVAL .. "s")
end

return exports
