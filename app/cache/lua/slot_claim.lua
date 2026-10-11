-- 原子抢占：先全量检查，再全量移除。
-- KEYS[1] = cg:avail:release:{rid}        (Set)
-- KEYS[2] = cg:booked:user:{uid}:release  (String int, 限购计数)
-- ARGV[1] = quantity
-- ARGV[2] = per_user_limit
-- ARGV[3..] = court_slot_id 列表
-- 返回 0=成功 1=有时段不可约 2=超过限购 3=集合未初始化
if redis.call('EXISTS', KEYS[1]) == 0 then return 3 end
for i = 3, #ARGV do
  if redis.call('SISMEMBER', KEYS[1], ARGV[i]) == 0 then return 1 end
end
local qty = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local bought = tonumber(redis.call('GET', KEYS[2]) or '0')
if bought + qty > limit then return 2 end
for i = 3, #ARGV do
  redis.call('SREM', KEYS[1], ARGV[i])
end
redis.call('SET', KEYS[2], bought + qty)
return 0
