local source = io.open(arg[1]):read("a")
local body = source:match("(local function chosen_index.-\nend\n)")
local chosen_index = load(body .. "\nreturn chosen_index")()

local function bits(text)
    local list = {}
    for i = 1, #text do
        list[i] = text:sub(i, i) == "1"
    end
    return list
end

local cases = {
    {"first meow of a fresh cue", nil, {bits = bits("00000000000100000000000000000000"), count = 1}, 12},
    {"other group's first pick", {bits = bits("0000000000000000"), count = 0}, {bits = bits("0000000000000100"), count = 1}, 14},
    {"second pick in the same group", {bits = bits("00000000000100000000000000000000"), count = 1},
        {bits = bits("00000000000100000000000000010000"), count = 2}, 28},
    {"group not picked", {bits = bits("000000000000000"), count = 0}, {bits = bits("000000000000000"), count = 0}, nil},
    {"reset after every recording was used", {bits = bits("111111"), count = 6}, {bits = bits("001000"), count = 1}, 3},
}

local failed = 0
for _, case in ipairs(cases) do
    local got = chosen_index(case[2], case[3])
    if got ~= case[4] then
        failed = failed + 1
    end
    print((got == case[4] and "ok   " or "FAIL ") .. case[1] .. " -> " .. tostring(got))
end
os.exit(failed == 0 and 0 or 1)
