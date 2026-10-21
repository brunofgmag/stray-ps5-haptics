local TAG = "[StrayHaptics] "
local CONTROLLER_CLASS = "/Game/Technical/BP_HKPlayerController.BP_HKPlayerController_C"
local TRIGGERS_FUNCTION = "/Script/Hk_project.HKPlayerController:SetPS5TriggersState"
local SPEAKER_OWNER = "BP_CatPawn_C"
local LEVEL_EPSILON = 0.01

local function log(message)
    print(TAG .. message .. "\n")
end

local function mod_directory()
    local source = debug.getinfo(1, "S").source:gsub("^@", "")
    return source:match("^(.*)[/\\]Scripts[/\\]main%.lua$") or "ue4ss/Mods/StrayHaptics"
end

local events_path = mod_directory() .. "\\events.log"
local events = io.open(events_path, "w")
if not events then
    log("could not open " .. events_path)
end

local function emit(...)
    if not events then
        return
    end
    local fields = {}
    for i = 1, select("#", ...) do
        fields[i] = tostring((select(i, ...)))
    end
    events:write(table.concat(fields, "\t"), "\n")
    events:flush()
end

local function valid(object)
    return object ~= nil and type(object) == "userdata" and object.IsValid ~= nil and object:IsValid()
end

local function object_name(object)
    return valid(object) and object:GetFName():ToString() or nil
end

local function path_of(object)
    return valid(object) and object:GetFullName():match("^%S+ (.+)$") or nil
end

local function resolve(path)
    if not path then
        return nil
    end
    local object = StaticFindObject(path)
    return valid(object) and object or nil
end

local function is_controller_sound(name)
    return name:find("_VIBE$") or name:find("_CONTROL$") or name == "strongLight_refilled"
end

local tracked = {}
local last_level = {}

local function start_voice(path, sound, fade, level, kind)
    if not (path and sound) then
        return
    end
    tracked[path] = kind
    last_level[path] = level
    emit("START", path, sound, fade, level)
end

local function stop_voice(path, fade)
    if tracked[path] then
        tracked[path] = nil
        last_level[path] = nil
        emit("STOP", path, fade or 0)
    end
end

local function set_level(path, level)
    local previous = last_level[path]
    if previous == nil or math.abs(previous - level) >= LEVEL_EPSILON or (level == 0 and previous ~= 0) then
        last_level[path] = level
        emit("LEVEL", path, level)
    end
end

local function parameter_names(path)
    local names = {}
    local func = StaticFindObject(path)
    if valid(func) then
        func:ForEachProperty(function(property)
            names[#names + 1] = property:GetFName():ToString()
        end)
    end
    return names
end

local function bind(names, params)
    local values = {}
    for index, name in ipairs(names) do
        local param = params[index]
        if param then
            local ok, value = pcall(function() return param:get() end)
            if ok then
                values[name:lower()] = value
            end
        end
    end
    return values
end

local function pick(values, fragment)
    for name, value in pairs(values) do
        if name:find(fragment) then
            return value
        end
    end
end

local function controller_component(context, property)
    local ok, controller = pcall(function() return context:get() end)
    if ok and valid(controller) then
        local component = controller[property]
        if valid(component) then
            return component
        end
    end
end

local function handler(function_name, names)
    local on_component = function_name:find("OnAudioComponent$") ~= nil
    local default_property = function_name:find("ControllerSound") and "ControllerAudio" or "ControllerVibration"
    return function(context, ...)
        local values = bind(names, {...})
        local component = on_component and pick(values, "component") or controller_component(context, default_property)
        local path = path_of(component)
        if not path then
            return
        end
        if function_name:find("^Start") then
            start_voice(path, object_name(pick(values, "sound")), tonumber(pick(values, "fade")) or 0,
                tonumber(pick(values, "level")) or 1, "bp")
        elseif function_name:find("^Stop") then
            stop_voice(path, tonumber(pick(values, "fade")) or 0)
        elseif function_name:find("Level") then
            set_level(path, tonumber(pick(values, "level")) or 0)
        elseif function_name:find("Paused") then
            emit("PAUSE", path, pick(values, "pause") and 1 or 0)
        end
    end
end

local FUNCTIONS = {
    "StartPS5Vibration", "StopPS5Vibration", "SetPS5VibrationLevel", "SetPS5VibrationPaused",
    "StartPS5VibrationOnAudioComponent", "StopPS5VibrationOnAudioComponent",
    "SetPS5VibrationLevelOnAudioComponent", "SetPS5VibrationPausedOnAudioComponent",
    "StartPS5ControllerSound", "StopPS5ControllerSound", "SetPS5ControllerSoundLevel",
    "StartPS5ControllerSoundOnAudioComponent", "StopPS5ControllerSoundOnAudioComponent",
    "SetPS5ControllerSoundLevelOnAudioComponent",
}

local paused = false

local function set_paused(now_paused)
    if now_paused ~= paused then
        paused = now_paused
        emit("PAUSEALL", paused and 1 or 0)
    end
end

local function register_hooks()
    for _, function_name in ipairs(FUNCTIONS) do
        local path = CONTROLLER_CLASS .. ":" .. function_name
        local names = parameter_names(path)
        local ok, err = pcall(RegisterHook, path, handler(function_name, names))
        log((ok and "hooked " or "hook failed ") .. function_name .. " (" .. table.concat(names, ", ") .. ")"
            .. (ok and "" or (" " .. tostring(err))))
    end
    RegisterHook("/Script/Engine.AudioComponent:Play", function(context)
        local component = context:get()
        local sound = valid(component) and object_name(component.Sound)
        local path = path_of(component)
        if sound and path and is_controller_sound(sound) and tracked[path] ~= "bp" then
            start_voice(path, sound, 0, tonumber(component.VolumeMultiplier) or 1, "play")
        end
    end)
    RegisterHook("/Script/Engine.AudioComponent:Stop", function(context)
        local path = path_of(context:get())
        if path and tracked[path] == "play" then
            stop_voice(path, 0)
        end
    end)
    RegisterHook("/Script/Engine.AudioComponent:FadeOut", function(context, duration)
        local path = path_of(context:get())
        if path and tracked[path] == "play" then
            stop_voice(path, tonumber(duration:get()) or 0)
        end
    end)
    RegisterHook("/Script/Engine.GameplayStatics:SetGamePaused", function(context, world, now_paused)
        set_paused(now_paused:get() and true or false)
    end)
    local ok, err = pcall(RegisterHook, TRIGGERS_FUNCTION, function(context, state, side)
        local state_ok, state_value = pcall(function() return state:get() end)
        local side_ok, side_value = pcall(function() return side:get() end)
        if state_ok and side_ok then
            emit("TRIGGERS", state_value, side_value)
        end
    end)
    log((ok and "hooked " or "hook failed ") .. TRIGGERS_FUNCTION .. (ok and "" or (" " .. tostring(err))))
end

local function load_speaker_cues()
    local cues = {}
    local file = io.open(mod_directory() .. "\\speaker_cues.txt", "r")
    if not file then
        log("no speaker_cues.txt, meows stay off the controller speaker")
        return cues
    end
    for line in file:lines() do
        local name, level = line:match("^([^\t]+)\t([%d%.]+)")
        if name then
            cues[name] = tonumber(level) or 1
        end
    end
    file:close()
    return cues
end

local speaker_cues = load_speaker_cues()
local random_state = {}

local function node_class(node)
    return node:GetClass():GetFName():ToString()
end

local function children(node)
    local list = {}
    pcall(function()
        node.ChildNodes:ForEach(function(_, element)
            list[#list + 1] = element:get()
        end)
    end)
    return list
end

local function random_nodes(node, found, depth)
    if not valid(node) or depth > 8 then
        return found
    end
    if node_class(node) == "SoundNodeRandom" then
        found[#found + 1] = node
    end
    for _, child in ipairs(children(node)) do
        random_nodes(child, found, depth + 1)
    end
    return found
end

local function read_random(node)
    local bits = {}
    pcall(function()
        node.HasBeenUsed:ForEach(function(_, element)
            bits[#bits + 1] = element:get() and true or false
        end)
    end)
    return {bits = bits, count = tonumber(node.NumRandomUsed) or 0}
end

local function snapshot(cue)
    local state = {}
    for _, node in ipairs(random_nodes(cue.FirstNode, {}, 0)) do
        state[node:GetFullName()] = read_random(node)
    end
    random_state[cue:GetFullName()] = state
end

local function chosen_index(before, after)
    before = before or {bits = {}, count = 0}
    local newly = {}
    for i, used in ipairs(after.bits) do
        if used and not before.bits[i] then
            newly[#newly + 1] = i
        end
    end
    if #newly == 1 then
        return newly[1]
    end
    if after.count < before.count or (#newly == 0 and after.count ~= before.count) then
        local set = {}
        for i, used in ipairs(after.bits) do
            if used then
                set[#set + 1] = i
            end
        end
        if #set == 1 then
            return set[1]
        end
    end
    return nil
end

local function newly_used(before, after)
    before = before or {bits = {}, count = 0}
    for i, used in ipairs(after.bits) do
        if used and not before.bits[i] then
            return i
        end
    end
    return nil
end

local function bit_text(state)
    state = state or {bits = {}, count = 0}
    local chars = {}
    for i, used in ipairs(state.bits) do
        chars[i] = used and "1" or "0"
    end
    return table.concat(chars) .. "/" .. tostring(state.count)
end

local function wave_of(node)
    local wave = valid(node) and node.SoundWave
    return valid(wave) and wave:GetFName():ToString() or nil
end

local function resolve_wave(cue, before)
    for _, node in ipairs(random_nodes(cue.FirstNode, {}, 0)) do
        local list = children(node)
        if #list > 0 and node_class(list[1]) == "SoundNodeWavePlayer" then
            local index = chosen_index(before[node:GetFullName()], read_random(node))
            if index and list[index] then
                return wave_of(list[index]), not valid(list[index])
            end
        end
    end
    local first = cue.FirstNode
    for _ = 1, 8 do
        if not valid(first) then
            break
        end
        if node_class(first) == "SoundNodeWavePlayer" then
            return wave_of(first)
        end
        local list = children(first)
        if #list ~= 1 then
            break
        end
        first = list[1]
    end
    return nil
end

local function guess_wave(cue, before)
    local candidates = {}
    for _, node in ipairs(random_nodes(cue.FirstNode, {}, 0)) do
        local list = children(node)
        if #list > 0 and node_class(list[1]) == "SoundNodeWavePlayer" then
            local previous = before[node:GetFullName()]
            candidates[#candidates + 1] = {list = list, before = previous, after = read_random(node)}
        end
    end
    local states = {}
    for _, candidate in ipairs(candidates) do
        states[#states + 1] = bit_text(candidate.before) .. " -> " .. bit_text(candidate.after)
    end
    local picked, index, reason = nil, nil, nil
    for _, candidate in ipairs(candidates) do
        index = newly_used(candidate.before, candidate.after)
        if index and candidate.list[index] then
            picked, reason = candidate, "first new"
            break
        end
    end
    if not picked and candidates[1] then
        picked, index, reason = candidates[1], math.random(#candidates[1].list), "random"
    end
    local wave = picked and wave_of(picked.list[index])
    log("guessed " .. tostring(wave) .. " (" .. tostring(reason) .. ") for " .. cue:GetFName():ToString()
        .. ": " .. table.concat(states, " | "))
    return wave
end

local function snapshot_loaded_cues()
    for _, cue in ipairs(FindAllOf("SoundCue") or {}) do
        if valid(cue) and speaker_cues[cue:GetFName():ToString()] then
            snapshot(cue)
        end
    end
end

local function speak(component_path, attempt)
    local component = resolve(component_path)
    local cue = component and component.Sound
    if not valid(cue) then
        return
    end
    local cue_name = cue:GetFName():ToString()
    local level = speaker_cues[cue_name]
    if not level then
        return
    end
    local before = random_state[cue:GetFullName()] or {}
    local wave, empty = resolve_wave(cue, before)
    if empty then
        snapshot(cue)
        log("drew an empty slot of " .. cue_name .. ", the game plays nothing there either")
        return
    end
    if not wave and attempt < 4 then
        ExecuteWithDelay(40 * attempt, function()
            ExecuteInGameThread(function()
                speak(component_path, attempt + 1)
            end)
        end)
        return
    end
    if not wave then
        wave = guess_wave(cue, before)
    end
    snapshot(cue)
    if wave then
        start_voice(component_path, wave, 0, level, "play")
    else
        log("could not resolve the recording of " .. cue_name)
    end
end

local function watch_new_components()
    NotifyOnNewObject("/Script/Engine.AudioComponent", function(component)
        local full = component:GetFullName()
        if not full:find(SPEAKER_OWNER, 1, true) then
            return
        end
        local component_path = full:match("^%S+ (.+)$")
        ExecuteWithDelay(20, function()
            ExecuteInGameThread(function()
                speak(component_path, 1)
            end)
        end)
    end)
end

local function poll()
    for path, kind in pairs(tracked) do
        local component = resolve(path)
        if not component then
            stop_voice(path, 0)
        elseif kind == "play" then
            local ok, playing = pcall(function() return component:IsPlaying() end)
            if ok and not playing then
                stop_voice(path, 0)
            end
        end
    end
end

emit("RESET")
log("writing events to " .. events_path)

local hooked = false
LoopAsync(250, function()
    ExecuteInGameThread(function()
        if not hooked and valid(StaticFindObject(CONTROLLER_CLASS)) then
            hooked = true
            register_hooks()
            watch_new_components()
            snapshot_loaded_cues()
        end
        local ok, err = pcall(poll)
        if not ok then
            log("poll error " .. tostring(err))
        end
    end)
    return false
end)
