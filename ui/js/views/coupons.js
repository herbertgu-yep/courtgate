window.VIEWS = window.VIEWS || {};
VIEWS.coupons = {
  template: `
  <div class="page">
    <div class="nav">
      <div class="back" @click="$back">${ICONS.back}</div>
      <div class="t"><div class="tt">领券中心</div><div class="ts">限量券先领先得，下单时直接抵扣</div></div>
    </div>
    <div class="sec-card glass" v-for="t in templates" :key="t.id">
      <div class="sec-row" style="margin-top:0">
        <div style="flex:1">
          <div class="tt">${ICONS.ticket} {{ t.name }}</div>
          <div class="sub">{{ ruleText(t) }} · 有效期至 {{ (t.valid_to || "").slice(0, 10) }} · 剩 {{ t.remaining }} 张</div>
        </div>
        <button class="bk-btn solid" @click="claim(t)" :disabled="t.remaining <= 0 || t.claimed">
          {{ t.claimed ? "已领取" : t.remaining <= 0 ? "已抢完" : "立即领取" }}</button>
      </div>
    </div>
    <div class="empty" v-if="!loading && !templates.length">${ICONS.ticket}暂无可领的优惠券</div>
    <div class="ok-box" v-if="tip" style="margin:12px 14px">{{ tip }}</div>
    <div class="err-box" v-if="err" style="margin:12px 14px">{{ err }}</div>
  </div>`,
  data: () => ({ templates: [], loading: true, tip: "", err: "" }),
  async mounted() { await this.load(); },
  methods: {
    async load() {
      this.templates = (await API.fetch("/api/coupons/templates")).items;
      this.loading = false;
    },
    ruleText(t) {
      if (t.type === "fixed") {
        const off = "立减 ¥" + (t.value / 100).toFixed(0);
        return t.min_spend_cents > 0 ? `满 ¥${(t.min_spend_cents / 100).toFixed(0)} ${off}` : off;
      }
      return "享 " + (t.value / 100).toFixed(1) + " 折";
    },
    async claim(t) {
      this.tip = ""; this.err = "";
      try {
        await API.fetch(`/api/coupons/${t.id}/claim`, { method: "POST" });
        t.claimed = true;
        t.remaining -= 1;
        this.tip = `领取成功：${t.name}，可在「我的」页查看`;
      } catch (e) {
        this.err = e.message;
        if (e.code === "COUPON_SOLD_OUT") t.remaining = 0;
      }
    },
  },
};
