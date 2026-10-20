local source = io.open(arg[1]):read("a")

local function extract(name)
    local body = source:match("(local function " .. name .. ".-\nend\n)")
    return load(body .. "\nreturn " .. name)()
end

local chosen_index = extract("chosen_index")
local newly_used = extract("newly_used")

local function bits(text)
    local list = {}
    for i = 1, #text do
        list[i] = text:sub(i, i) == "1"
    end
    return list
end

local cases = {
    {chosen_index, "first meow of a fresh cue", nil, {bits = bits("00000000000100000000000000000000"), count = 1}, 12},
    {chosen_index, "other group's first pick", {bits = bits("0000000000000000"), count = 0},
        {bits = bits("0000000000000100"), count = 1}, 14},
    {chosen_index, "second pick in the same group", {bits = bits("00000000000100000000000000000000"), count = 1},
        {bits = bits("00000000000100000000000000010000"), count = 2}, 28},
    {chosen_index, "group not picked", {bits = bits("000000000000000"), count = 0},
        {bits = bits("000000000000000"), count = 0}, nil},
    {chosen_index, "reset after every recording was used", {bits = bits("111111"), count = 6},
        {bits = bits("001000"), count = 1}, 3},
    {chosen_index, "two picks since the snapshot stay ambiguous", {bits = bits("000000"), count = 0},
        {bits = bits("010010"), count = 2}, nil},
    {newly_used, "two picks since the snapshot give the first new one", {bits = bits("000000"), count = 0},
        {bits = bits("010010"), count = 2}, 2},
    {newly_used, "recordings used before the snapshot are skipped", {bits = bits("110000"), count = 2},
        {bits = bits("110100"), count = 3}, 4},
    {newly_used, "no snapshot counts every used recording as new", nil, {bits = bits("001010"), count = 2}, 3},
    {newly_used, "nothing new", {bits = bits("010000"), count = 1}, {bits = bits("010000"), count = 1}, nil},
}

local failed = 0
for _, case in ipairs(cases) do
    local got = case[1](case[3], case[4])
    if got ~= case[5] then
        failed = failed + 1
    end
    print((got == case[5] and "ok   " or "FAIL ") .. case[2] .. " -> " .. tostring(got))
end
os.exit(failed == 0 and 0 or 1)
