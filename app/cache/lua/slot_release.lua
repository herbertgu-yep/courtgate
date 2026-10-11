-- 归还：单元加回集合，减少限购计数。
-- KEYS[1] = avail set, KEYS[2] = bought counter
-- ARGV[1] = quantity, ARGV[2..] = court_slot_ids
if redis.call('EXISTS', KEYS[1]) == 0 then return 1 end
for i = 2, #ARGV do
  redis.call('SADD', KEYS[1], ARGV[i])
end
local bought = tonumber(redis.call('GET', KEYS[2]) or '0')
local after = bought - tonumber(ARGV[1])
if after <= 0 then
  redis.call('DEL', KEYS[2])
else
  redis.call('SET', KEYS[2], after)
end
return 0
