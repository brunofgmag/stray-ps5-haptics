local source = io.open(arg[1]):read("a")

local function extract(name)
    local body = source:match("(local function " .. name .. ".-\nend\n)")
    return load(body .. "\nreturn " .. name)()
end

local later = extract("later_in_game_thread")
local every = extract("every_in_game_thread")

local calls

local function reset(with_game_thread_timers)
    calls = {async = 0, game_thread = 0, ran = 0}
    ExecuteWithDelay = function(_, callback)
        calls.async = calls.async + 1
        callback()
    end
    LoopAsync = function(_, callback)
        calls.async = calls.async + 1
        callback()
    end
    ExecuteInGameThread = function(callback) callback() end
    ExecuteInGameThreadWithDelay = nil
    LoopInGameThreadWithDelay = nil
    if with_game_thread_timers then
        ExecuteInGameThreadWithDelay = function(_, callback)
            calls.game_thread = calls.game_thread + 1
            callback()
        end
        LoopInGameThreadWithDelay = function(_, callback)
            calls.game_thread = calls.game_thread + 1
            callback()
        end
    end
end

local function ran()
    calls.ran = calls.ran + 1
end

local failed = 0

local function check(name, ok)
    if not ok then
        failed = failed + 1
    end
    print((ok and "ok   " or "FAIL ") .. name .. " -> async " .. calls.async .. " game thread " .. calls.game_thread
        .. " ran " .. calls.ran)
end

reset(true)
later(20, ran)
check("a delay runs on the game thread timer when UE4SS has one", calls.game_thread == 1 and calls.async == 0
    and calls.ran == 1)

reset(true)
every(250, ran)
check("a loop runs on the game thread timer when UE4SS has one", calls.game_thread == 1 and calls.async == 0
    and calls.ran == 1)

reset(false)
later(20, ran)
check("a delay falls back to the async timer on UE4SS 3.0.1", calls.async == 1 and calls.ran == 1)

reset(false)
every(250, ran)
check("a loop falls back to the async timer on UE4SS 3.0.1", calls.async == 1 and calls.ran == 1)

os.exit(failed == 0 and 0 or 1)
