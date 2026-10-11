window.VIEWS = window.VIEWS || {};
VIEWS.confirm = {
  template: `
  <div class="page">
    <div class="nav">
      <div class="back" @click="$back">${ICONS.back}</div>
      <div class="t"><div class="tt">确认预约</div><div class="ts">请在 15 分钟内完成支付</div></div>
    </div>
    <div class="sum-card glass">
      <div class="sum-item" v-for="s in items" :key="s.court_slot_id">
        <span class="l">${ICONS.calendar}{{ s.date.slice(5) }}（{{ s.court_name }}）{{ s.time_label }}</span>
        <b>¥{{ (s.price_cents / 100).toFixed(0) }}</b></div>
      <div class="kv"><span>原价小计</span><b>¥{{ (q.subtotal_cents / 100).toFixed(2) }}</b></div>
      <div class="kv" v-if="q.member_discount_cents"><span>会员折扣</span>
        <b class="neg">-¥{{ (q.member_discount_cents / 100).toFixed(2) }}</b></div>
      <div class="kv"><span>优惠券</span></div>
      <div class="inp">${ICONS.ticket}
        <select v-model="couponId" style="border:0;background:transparent;box-shadow:none;padding:0;width:auto;flex:1">
          <option :value="null">不使用</option>
          <option v-for="c in coupons" :value="c.id">{{ c.name }}（已领）</option>
        </select></div>
      <div class="kv" style="margin-top:8px"><span>积分抵扣（余额 {{ points }}，最多可用 {{ q.max_usable_points }}）</span></div>
      <div class="inp">${ICONS.coins}
        <input v-model.number="usePoints" type="number" :min="0" :max="q.max_usable_points || 0"
               style="border:0;background:transparent;box-shadow:none;padding:0;width:auto;flex:1"></div>
      <div class="total"><span class="lab">应付</span><span class="amt">¥{{ (q.total_cents / 100).toFixed(2) }}</span></div>
    </div>
    <div class="err-box" v-if="err">{{ err }}</div>
    <button class="big-cta" @click="submit" :disabled="busy || !q.total_cents">
      {{ busy ? "提交中…" : "提交预约" }}</button>
    <div class="hint">${ICONS.info}提交后 15 分钟内未支付将自动释放时段</div>
  </div>`,
  data: () => ({ releaseId: 0, slotIds: [], items: [], q: {}, coupons: [], points: 0,
                couponId: null, usePoints: 0, err: "", busy: false }),
  async mounted() {
    this.releaseId = parseInt(this.$route.match[2], 10);
    this.slotIds = (this.$route.query.slots || "").split(",").map(Number).filter(Boolean);
    await this.quote();
    try {
      this.coupons = (await API.fetch("/api/coupons/mine")).items.filter(c => c.status === "unused");
      this.points = (await API.fetch("/api/points/balance")).balance;
    } catch (e) { /* 未登录等 */ }
  },
  methods: {
    async quote() {
      const q = await API.fetch("/api/bookings/quote", {
        method: "POST", body: JSON.stringify({ release_id: this.releaseId,
          court_slot_ids: this.slotIds, coupon_id: this.couponId, use_points: this.usePoints })});
      this.q = q;
      this.items = q.items || this.items;
    },
    async refreshQuote() { await this.quote(); },
    async submit() {
      this.busy = true; this.err = "";
      const key = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
      try {
        const r = await API.fetch("/api/bookings", {
          method: "POST", headers: { "Idempotency-Key": key },
          body: JSON.stringify({ release_id: this.releaseId, court_slot_ids: this.slotIds,
                                 coupon_id: this.couponId, use_points: this.usePoints })});
        location.hash = "#/bookings";
      } catch (e) {
        this.err = e.message + (e.details && e.details.court_slot_ids ? "（该时段刚被抢走）" : "");
        await this.quote();
      } finally { this.busy = false; }
    },
  },
  watch: { couponId() { this.refreshQuote(); },
           usePoints() { clearTimeout(this._t); this._t = setTimeout(() => this.refreshQuote(), 400); } },
};
