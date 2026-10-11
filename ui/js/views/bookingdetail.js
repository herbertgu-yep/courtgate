window.VIEWS = window.VIEWS || {};
VIEWS.bookingdetail = {
  template: `
  <div class="page">
    <div class="nav">
      <div class="back" @click="$back">${ICONS.back}</div>
      <div class="t"><div class="tt">预约详情</div><div class="ts">{{ b.booking_no }}</div></div>
      <span class="tag" :class="statusTag(b.status)" v-if="b.booking_no">{{ statusText(b.status) }}</span>
    </div>
    <div class="sum-card glass" v-if="b.booking_no">
      <div class="sum-item" v-for="s in items" :key="s.court_slot_id">
        <span class="l">${ICONS.calendar}{{ s.slot_date.slice(5) }}（{{ s.court_name }}）{{ s.time_label }}</span>
        <b>¥{{ (s.price_cents / 100).toFixed(0) }}</b></div>
      <div class="kv"><span>原价小计</span><b>¥{{ (b.subtotal_cents / 100).toFixed(2) }}</b></div>
      <div class="kv" v-if="b.member_discount_cents"><span>会员折扣</span>
        <b class="neg">-¥{{ (b.member_discount_cents / 100).toFixed(2) }}</b></div>
      <div class="kv" v-if="b.coupon_discount_cents"><span>优惠券</span>
        <b class="neg">-¥{{ (b.coupon_discount_cents / 100).toFixed(2) }}</b></div>
      <div class="kv" v-if="b.points_discount_cents"><span>积分抵扣</span>
        <b class="neg">-¥{{ (b.points_discount_cents / 100).toFixed(2) }}</b></div>
      <div class="total"><span class="lab">实付</span><span class="amt">¥{{ (b.total_cents / 100).toFixed(2) }}</span></div>
    </div>
    <div class="sec-card glass" v-if="b.booking_no">
      <div class="kv"><span>下单时间</span><b>{{ shortTime(b.created_at) }}</b></div>
      <div class="kv" v-if="b.paid_at"><span>支付时间</span><b>{{ shortTime(b.paid_at) }}</b></div>
      <div class="kv" v-if="b.cancelled_at"><span>取消时间</span><b>{{ shortTime(b.cancelled_at) }}</b></div>
      <div class="kv" v-if="b.status === 'pending_paid'"><span>支付截止</span>
        <b style="color:var(--warn)">{{ shortTime(b.expire_at) }}</b></div>
    </div>
    <div class="err-box" v-if="err">{{ err }}</div>
    <div class="ok-box" v-if="ok">{{ ok }}</div>
    <div class="bk-btns" style="margin:12px 14px 0" v-if="b.booking_no">
      <template v-if="b.status === 'pending_paid'">
        <button class="big-cta" style="margin:0;width:auto;flex:1" @click="location.hash = '#/pay/' + b.booking_no">立即支付</button>
        <button class="big-cta line" style="margin:0;width:auto;flex:1" @click="cancel">取消预约</button>
      </template>
      <template v-else-if="b.status === 'paid'">
        <button class="big-cta line" style="margin:0" @click="cancel"
                :disabled="!canCancelPaid">{{ canCancelPaid ? "取消预约（原路退款）" : "开场前 2 小时内不可取消" }}</button>
      </template>
    </div>
  </div>`,
  data: () => ({ b: {}, items: [], err: "", ok: "" }),
  async mounted() {
    this.bookingNo = this.$route.match[2];
    try {
      const headers = { Authorization: "Bearer " + API.token };
      this.b = await API.fetch(`/api/bookings/${this.bookingNo}`, { headers });
      this.items = this.b.items || [];
    } catch (e) { this.err = e.message; }
  },
  computed: {
    canCancelPaid() {
      if (this.b.status !== "paid") return false;
      const hm = s => { const [h, m] = String(s || "00:00").split("-")[0].split(":").map(Number); return (h || 0) * 60 + (m || 0); };
      for (const it of this.items) {
        const start = new Date(it.slot_date + "T00:00:00+08:00").getTime() + hm(it.time_label) * 60000;
        if (start - Date.now() < 2 * 3600 * 1000) return false;
      }
      return this.items.length > 0;
    },
  },
  methods: {
    async cancel() {
      const isPaid = this.b.status === "paid";
      const tip = isPaid
        ? "已支付订单取消将原路退款，赠送积分同步扣回。确认取消该预约？"
        : "确认取消该预约？时段将立即释放。";
      if (!(await this.$root.confirm(tip, "取消预约", isPaid ? "取消并退款" : "确认取消"))) return;
      this.err = ""; this.ok = "";
      try {
        const r = await API.fetch(`/api/bookings/${this.bookingNo}/cancel`, { method: "POST" });
        this.b = r;
        this.ok = isPaid ? "已取消，款项将原路退回" : "已取消，时段已释放";
      } catch (e) { this.err = e.message; }
    },
    shortTime(t) { return (t || "").slice(0, 16).replace("T", " "); },
    statusText(s) { return { pending_paid: "待支付", paid: "已预约", refunded: "已退款", cancelled: "已取消", finished: "已完成" }[s] || s; },
    statusTag(s) { return { pending_paid: "pay", paid: "ok", refunded: "sand", cancelled: "cancel", finished: "ok" }[s] || ""; },
  },
};
