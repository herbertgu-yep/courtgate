-- 领券原子抢占（第二个秒杀）
-- KEYS[1] = 库存计数  KEYS[2] = 用户已领计数  ARGV[1] = 每人限领
-- 返回 0=成功 1=售罄 2=超限 3=未初始化
if redis.call('EXISTS', KEYS[1]) == 0 then return 3 end
local stock = tonumber(redis.call('GET', KEYS[1]))
if stock <= 0 then return 1 end
local claimed = tonumber(redis.call('GET', KEYS[2]) or '0')
if claimed + 1 > tonumber(ARGV[1]) then return 2 end
redis.call('DECR', KEYS[1])
redis.call('INCR', KEYS[2])
return 0
