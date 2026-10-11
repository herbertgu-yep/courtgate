# CourtGate

**面向小型商业运动场馆（羽毛球馆等）的场地分时预约系统。**

解决场馆方「约场难、排期易错、场地空置、对账繁琐」：管理员配置场馆与时段、按批次开放预约；
顾客在线选时段预约，未支付自动取消，并发抢约不重复占用。

## 功能

- **分时预约**：日历选场地选时段、多时段合并下单、15 分钟未支付自动取消
- **并发抢约**：开抢瞬间多用户争抢同一时段，不超卖、不重复占用
- **会员与积分**：按累计消费自动升级折扣，支付赠积分、下单可抵扣
- **优惠券**：限量发放、先领先得、下单核销，取消/退款自动返还
- **管理端**：场馆配置（营业时间/休息窗口/高峰时段/预约粒度/场地单价）、按批次放场、
  休息日处理（自动取消/退款/通知）、经营统计
- **通知**：预约/支付/取消/闭馆等事件站内信送达，可选邮件扩展

内置演示账号：管理员 `admin / Admin@123456`，顾客 `user1 ~ user5 / User@123456`。

## 快速开始（本地）

```bash
# 1. 基础设施（MySQL 8 + Redis 7）
docker compose -f docker/docker-compose.yml up -d mysql redis

# 2. 安装与建表
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head

# 3. 演示数据（场馆/场地/时段/账号）
python -m scripts.seed

# 4. 起服务
uvicorn app.main:app --port 8000
```

浏览器打开 `http://127.0.0.1:8000/`（响应式 H5，手机体验最佳），
接口文档在 `/docs`。局域网演示改用 `--host 0.0.0.0`，同 WiFi 手机访问
`http://<本机局域网IP>:8000`。

## 部署到云服务器（公网访问）

准备：一台最低配云服务器（阿里云/腾讯云轻量 1C1G 即可）+ 已放行 22/80/443 端口的安全组。
域名可选：没有域名时用 `http://服务器IP:8000` 直接访问；有域名时按第 4 步启用自动 HTTPS。

```bash
# 1. 服务器上安装 Docker（Ubuntu/Debian/CentOS 通用）
curl -fsSL https://get.docker.com | bash

# 2. 拿到代码（git clone 你的仓库，或 scp 整个目录上去）
git clone https://github.com/herbertgu-yep/courtgate.git && cd courtgate

# 3. 配置：改两把密钥（必须），有域名则记下待用
cp .env.example .env
vi .env   # 至少修改 COURTGATE_JWT_SECRET 与 COURTGATE_PAYMENT_SECRET（openssl rand -hex 32）

# 4. 起全套（MySQL/Redis/建表/API/Celery worker/beat 一次到位）
docker compose -f docker/docker-compose.yml up -d

# 5. 初始化演示数据（可选）
docker compose exec api python -m scripts.seed

# 6. 验证
curl http://服务器IP:8000/healthz        # {"status":"ok",...}
浏览器打开 http://服务器IP:8000           # 手机访问体验最佳
```

**启用 HTTPS（有域名时，推荐）**：把域名 A 记录解析到服务器 IP，然后

```bash
COURTGATE_DOMAIN=app.example.com \
docker compose -f docker/docker-compose.yml -f docker/docker-compose.public.yml up -d
```

Caddy 会自动申请并续期 Let's Encrypt 证书，之后通过 `https://app.example.com` 访问；
建议同时在云安全组只放行 22/80/443。

**上线前清单**：

- [ ] `COURTGATE_JWT_SECRET` / `COURTGATE_PAYMENT_SECRET` 换成随机值（`openssl rand -hex 32`）
- [ ] 修改演示账号密码（`admin` 与 `user1 ~ user5`），或删库重建后只留自己的账号
- [ ] 修改 compose 中 MySQL 口令并同步 `COURTGATE_*_DATABASE_URL`
- [ ] 数据定期备份：`docker compose exec mysql mysqldump -uroot -proot courtgate > backup.sql`

**版本升级**：`git pull` 后重新构建并滚动重启（建表迁移自动执行）：

```bash
docker compose -f docker/docker-compose.yml build && \
docker compose -f docker/docker-compose.yml up -d
```

## 支付接入

支付渠道以 `PaymentChannel` 抽象接入（`app/services/payment/`）。内置 Mock 渠道开箱可用，
完整走通「创建支付单 → 回调验签 → 订单状态机 → 退款」全流程；
接入真实支付宝/微信只需实现一个类并注册，业务代码零改动。
验签算法、回调契约与接入步骤见 [docs/PAYMENT_INTEGRATION.md](docs/PAYMENT_INTEGRATION.md)。

## License

MIT
