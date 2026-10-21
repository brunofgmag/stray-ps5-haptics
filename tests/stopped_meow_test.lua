local source = io.open(arg[1]):read("a")

local function extract(name)
    local body = source:match("(local function " .. name .. ".-\nend\n)")
    return load(body .. "\nreturn " .. name)()
end

local function bits(text)
    local list = {}
    for i = 1, #text do
        list[i] = text:sub(i, i) == "1"
    end
    return list
end

local function slot(wave)
    return {class = "SoundNodeWavePlayer", wave = wave}
end

local unchanged = {
    class = "SoundNodeRandom",
    slots = {slot("alt01"), slot("alt02")},
    before = {bits = bits("01"), count = 1},
    after = {bits = bits("01"), count = 1},
    GetFullName = function() return "SoundNodeRandom cat_meow_come_on_01_Cue.Random" end,
}

local cue = {
    FirstNode = {class = "SoundNodeModulator", randoms = {unchanged}, slots = {}},
    GetFName = function() return {ToString = function() return "cat_meow_come_on_01_Cue" end} end,
    GetFullName = function() return "SoundCue cat_meow_come_on_01_Cue" end,
}

function valid(object)
    return type(object) == "table"
end

function node_class(node)
    return node.class
end

function children(node)
    return node.slots or {}
end

function random_nodes(first)
    return first.randoms or {}
end

function read_random(node)
    return node.after
end

function wave_of(node)
    return valid(node) and node.wave or nil
end

chosen_index = extract("chosen_index")
resolve_wave = extract("resolve_wave")
stopped = extract("stopped")
local speak = extract("speak")

local calls

local function reset(is_playing)
    calls = {delays = 0, guesses = 0, snapshots = 0, started = {}, logs = {}}
    speaker_cues = {cat_meow_come_on_01_Cue = 1.0}
    random_state = {[cue:GetFullName()] = {[unchanged:GetFullName()] = unchanged.before}}
    resolve = function() return {Sound = cue, IsPlaying = is_playing} end
    ExecuteWithDelay = function() calls.delays = calls.delays + 1 end
    ExecuteInGameThread = function(callback) callback() end
    guess_wave = function()
        calls.guesses = calls.guesses + 1
        return "alt02"
    end
    snapshot = function() calls.snapshots = calls.snapshots + 1 end
    start_voice = function(_, wave) calls.started[#calls.started + 1] = wave end
    log = function(message) calls.logs[#calls.logs + 1] = message end
end

local function is_stopped() return false end
local function is_playing() return true end
local function is_unknown() error("IsPlaying is not callable") end

local failed = 0

local function check(name, ok, detail)
    if not ok then
        failed = failed + 1
    end
    print((ok and "ok   " or "FAIL ") .. name .. " -> " .. tostring(detail))
end

local function summary()
    return "started " .. #calls.started .. " delays " .. calls.delays .. " guesses " .. calls.guesses
        .. " snapshots " .. calls.snapshots .. " log " .. tostring(calls.logs[1])
end

check("a component the game stopped counts as stopped", stopped({IsPlaying = is_stopped}) == true, "")
check("a playing component does not", stopped({IsPlaying = is_playing}) == false, "")
check("an unreadable component does not", stopped({IsPlaying = is_unknown}) == false, "")

reset(is_stopped)
speak("component", 4)
check("a meow the game already stopped is not guessed",
    #calls.started == 0 and calls.guesses == 0 and calls.snapshots == 1
        and (calls.logs[1] or ""):find("stopped") ~= nil,
    summary())

reset(is_playing)
speak("component", 4)
check("a meow still playing is guessed as before",
    calls.guesses == 1 and calls.started[1] == "alt02", summary())

reset(is_unknown)
speak("component", 4)
check("a meow whose state cannot be read is guessed as before",
    calls.guesses == 1 and calls.started[1] == "alt02", summary())

reset(is_stopped)
speak("component", 1)
check("a stopped meow still gets the retries before the guess",
    calls.delays == 1 and calls.guesses == 0 and #calls.started == 0, summary())

os.exit(failed == 0 and 0 or 1)
