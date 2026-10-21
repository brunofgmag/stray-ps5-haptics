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

local EMPTY = {empty = true}

local function random_node(slots, before, after)
    return {
        class = "SoundNodeRandom",
        slots = slots,
        before = {bits = bits(before), count = select(2, before:gsub("1", ""))},
        after = {bits = bits(after), count = select(2, after:gsub("1", ""))},
        GetFullName = function(self) return tostring(self) end,
    }
end

local function cue_with(randoms)
    local before = {}
    for _, node in ipairs(randoms) do
        before[node:GetFullName()] = node.before
    end
    local cue = {
        FirstNode = {class = "SoundNodeModulator", randoms = randoms, slots = {}},
        GetFName = function() return {ToString = function() return "cat_meow_come_on_01_Cue" end} end,
        GetFullName = function() return "SoundCue cat_meow_come_on_01_Cue" end,
    }
    return cue, before
end

function valid(object)
    return type(object) == "table" and not object.empty
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
local speak = extract("speak")

local calls

local function reset(cue, before)
    calls = {delays = 0, guesses = 0, snapshots = 0, started = {}, logs = {}}
    speaker_cues = {cat_meow_come_on_01_Cue = 1.0}
    random_state = {[cue:GetFullName()] = before}
    resolve = function() return {Sound = cue} end
    ExecuteWithDelay = function() calls.delays = calls.delays + 1 end
    ExecuteInGameThread = function(callback) callback() end
    guess_wave = function() calls.guesses = calls.guesses + 1 end
    snapshot = function() calls.snapshots = calls.snapshots + 1 end
    start_voice = function(_, wave) calls.started[#calls.started + 1] = wave end
    log = function(message) calls.logs[#calls.logs + 1] = message end
end

local three = {slot("alt01"), slot("alt02"), EMPTY}
local drew_recording = {random_node(three, "000", "010")}
local drew_empty = {random_node(three, "000", "001")}
local drew_nothing = {random_node(three, "000", "000")}

local failed = 0

local function check(name, ok, detail)
    if not ok then
        failed = failed + 1
    end
    print((ok and "ok   " or "FAIL ") .. name .. " -> " .. tostring(detail))
end

local cue, before = cue_with(drew_recording)
local wave, empty = resolve_wave(cue, before)
check("a drawn recording resolves to its wave", wave == "alt02" and not empty, tostring(wave) .. " " .. tostring(empty))

cue, before = cue_with(drew_empty)
wave, empty = resolve_wave(cue, before)
check("a drawn empty slot is told apart from an unresolved draw", wave == nil and empty == true,
    tostring(wave) .. " " .. tostring(empty))

cue, before = cue_with(drew_nothing)
wave, empty = resolve_wave(cue, before)
check("no new mark stays unresolved", wave == nil and not empty, tostring(wave) .. " " .. tostring(empty))

cue, before = cue_with(drew_empty)
reset(cue, before)
speak("component", 1)
check("an empty draw plays nothing, without retrying or guessing",
    #calls.started == 0 and calls.delays == 0 and calls.guesses == 0 and calls.snapshots == 1
        and (calls.logs[1] or ""):find("empty slot") ~= nil,
    "started " .. #calls.started .. " delays " .. calls.delays .. " guesses " .. calls.guesses
        .. " snapshots " .. calls.snapshots .. " log " .. tostring(calls.logs[1]))

cue, before = cue_with(drew_recording)
reset(cue, before)
speak("component", 1)
check("a drawn recording is played", calls.started[1] == "alt02" and calls.delays == 0, tostring(calls.started[1]))

cue, before = cue_with(drew_nothing)
reset(cue, before)
speak("component", 1)
check("an unresolved draw is retried", calls.delays == 1 and #calls.started == 0, "delays " .. calls.delays)

os.exit(failed == 0 and 0 or 1)
