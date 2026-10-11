-- 滑动窗口限流。
-- KEYS[1] = 限流键
-- ARGV[1] = 窗口毫秒  ARGV[2] = 上限  ARGV[3] = 当前毫秒时间戳  ARGV[4] = 唯一成员
local now = tonumber(ARGV[3])
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)
if redis.call('ZCARD', KEYS[1]) >= limit then
  return 0
end
redis.call('ZADD', KEYS[1], now, ARGV[4])
redis.call('PEXPIRE', KEYS[1], window)
return 1
