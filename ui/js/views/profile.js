window.VIEWS = window.VIEWS || {};
VIEWS.profile = {
  template: `
  <div class="page">
    <div class="nav">
      <div class="t" style="padding-left:2px"><div class="tt">我的</div></div>
      <a class="u" href="javascript:;" @click="logout" style="text-decoration:none;cursor:pointer">
        ${ICONS.logout} 退出</a>
    </div>
    <div class="me-card glass">
      <div class="avatar">${ICONS.user}</div>
      <div>
        <div class="me-name">{{ $root.nickname || me.level_name || "用户" }}
        <button class="bk-btn line" style="margin-left:8px" @click="openEdit">${ICONS.tool} 编辑资料</button></div>
        <div class="me-lvl">{{ me.level_name || "普通会员" }}
          <em v-if="me.next_level">再消费 ¥{{ (me.next_level.need_cents / 100).toFixed(0) }} 升 {{ me.next_level.name }}</em></div>
      </div>
    </div>
    <div class="modal-mask" v-if="editing">
      <div class="modal glass">
        <div class="tt">编辑资料</div>
        <label class="fl" style="margin-top:10px">昵称</label>
        <input v-model="edit.nickname" maxlength="20" placeholder="1~20 个字符">
        <label class="fl">手机号（用于场馆联系，选填）</label>
        <input v-model="edit.phone" maxlength="11" inputmode="numeric" placeholder="11 位手机号">
        <div class="err-box" v-if="editErr">{{ editErr }}</div>
        <div class="bk-btns" style="margin-top:14px">
          <button class="big-cta line" style="margin:0" @click="editing = false">取消</button>
          <button class="big-cta" style="margin:0" @click="saveProfile">保存</button>
        </div>
      </div>
    </div>
    <div class="me-stats glass">
      <div class="me-stat"><div class="v">{{ points }}</div><div class="k">积分余额</div></div>
      <div class="me-stat"><div class="v">{{ bookingsCount }}</div><div class="k">预约记录</div></div>
      <div class="me-stat"><div class="v">{{ coupons.filter(c => c.status === "unused").length }}</div><div class="k">可用优惠券</div></div>
    </div>
    <div class="sec-card glass">
      <div class="sec-t">优惠券<a href="#/coupons">领券中心 ${ICONS.chevR}</a></div>
      <div class="sec-row" v-for="c in coupons" :key="c.id">
        <div><div class="tt">${ICONS.ticket} {{ couponText(c) }}</div>
          <div class="sub">有效期至 {{ (c.expire_at || "").slice(0, 10) }} · 券码 {{ c.code }}</div></div>
        <span class="tag" :class="{ unused: 'ok', used: 'cancel', expired: 'cancel' }[c.status] || ''">
          {{ { unused: "未使用", used: "已使用", expired: "已过期" }[c.status] || c.status }}</span></div>
      <div class="empty" v-if="!coupons.length">${ICONS.ticket}暂无优惠券，去领券中心领取</div>
    </div>
    <div class="sec-card glass">
      <div class="sec-t">站内信<span v-if="unread">{{ unread }} 条未读 ·
        <a href="javascript:;" @click="readAll">全部已读</a></span><span v-else>支付、取消、开抢提醒都在这里</span></div>
      <div class="sec-row" v-for="n in notifications" :key="n.id" :class="{ unread: !n.is_read }"
           @click="openNotification(n)" style="cursor:pointer">
        <div><div class="tt">${ICONS.mail} {{ n.title }}</div>
          <div class="sub">{{ n.content.slice(0, 40) }}</div></div>
        <span class="tag ok" v-if="!n.is_read">新</span></div>
      <div class="empty" v-if="!notifications.length">${ICONS.mail}暂无消息</div>
    </div>
    <a class="admin-entry glass" href="#/mvenues" v-if="$root.admin">
      ${ICONS.tool} 场馆管理（场馆 · 放场 · 休息日）<span class="chev">${ICONS.chevR}</span></a>
    <a class="admin-entry glass" href="#/mcoupons" v-if="$root.admin">
      ${ICONS.gift} 优惠券管理（发券 · 库存）<span class="chev">${ICONS.chevR}</span></a>
    <div style="height:12px"></div>
    <div class="modal-mask" v-if="detail">
      <div class="modal glass">
        <div class="tt">${ICONS.mail} {{ detail.title }}</div>
        <div class="muted" style="margin:6px 0 10px">{{ (detail.created_at || "").slice(0, 16).replace("T", " ") }}</div>
        <div style="font-size:13.5px;line-height:1.8;color:#33473c">{{ detail.content }}</div>
        <button class="big-cta" style="margin-top:16px" @click="detail = null">关闭</button>
      </div>
    </div>
  </div>`,
  data: () => ({ me: {}, points: 0, coupons: [], notifications: [], bookingsCount: 0,
                 editing: false, edit: { nickname: "", phone: "" }, editErr: "", detail: null }),
  computed: {
    unread() { return this.notifications.filter(n => !n.is_read).length; },
  },
  async mounted() {
    try {
      this.me = { ...(await API.fetch("/api/members/me")), phone_number: (await API.fetch("/api/auth/me")).phone_number };
      this.points = (await API.fetch("/api/points/balance")).balance;
      this.coupons = (await API.fetch("/api/coupons/mine")).items;
      this.notifications = (await API.fetch("/api/notifications")).items;
      this.bookingsCount = (await API.fetch("/api/bookings?size=1")).total;
    } catch (e) { /* 各区块独立展示，单项失败不阻塞整页 */ }
  },
  methods: {
    couponText(c) {
      const val = c.type === "fixed" ? `立减 ¥${(c.value / 100).toFixed(0)}`
        : c.type === "percent" ? `享 ${(c.value / 100).toFixed(1)} 折` : "";
      const min = c.min_spend_cents > 0 ? `满 ¥${(c.min_spend_cents / 100).toFixed(0)} 可用 · ` : "";
      return `${c.name || "优惠券"}（${min}${val}）`;
    },
    openEdit() {
      this.edit = { nickname: this.$root.nickname || "", phone: this.me.phone_number || "" };
      this.editErr = "";
      this.editing = true;
    },
    async saveProfile() {
      this.editErr = "";
      if (!this.edit.nickname.trim()) { this.editErr = "昵称不能为空"; return; }
      if (this.edit.phone && !/^1[3-9]\d{9}$/.test(this.edit.phone)) { this.editErr = "手机号格式不正确"; return; }
      try {
        const r = await API.fetch("/api/auth/me", { method: "PATCH",
          body: JSON.stringify({ nickname: this.edit.nickname.trim(), phone_number: this.edit.phone })});
        this.$root.nickname = r.nickname;
        localStorage.setItem("cg_nickname", r.nickname);
        this.me.phone_number = r.phone_number;
        this.editing = false;
      } catch (e) { this.editErr = e.message; }
    },
    async openNotification(n) {
      this.detail = n;
      if (!n.is_read) {
        try {
          await API.fetch(`/api/notifications/${n.id}/read`, { method: "POST" });
        } catch (e) { /* 已读失败不打断查看 */ }
        n.is_read = 1;
      }
    },
    async read(n) {
      if (!n.is_read) await API.fetch(`/api/notifications/${n.id}/read`, { method: "POST" });
      n.is_read = 1;
    },
    async readAll() {
      await API.fetch("/api/notifications/read-all", { method: "POST" });
      this.notifications.forEach(n => { n.is_read = 1; });
    },
    logout() { this.$root.logout(); },
  },
};
