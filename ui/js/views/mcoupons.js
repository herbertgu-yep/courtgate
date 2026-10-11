/* 优惠券管理：发券（创建券模板）+ 模板列表（库存/领取进度） */
window.VIEWS = window.VIEWS || {};
VIEWS.mcoupons = {
  template: `
  <div class="page">
    <div class="nav">
      <div class="back" @click="$back">${ICONS.back}</div>
      <div class="t"><div class="tt">优惠券管理</div><div class="ts">创建券模板后，用户即可在领券中心领取</div></div>
    </div>
    <div class="form-card glass">
      <label class="fl">券名</label>
      <input v-model="f.name" maxlength="50" placeholder="如：新客立减 10 元">
      <label class="fl">类型</label>
      <select v-model="f.type">
        <option value="fixed">满减（立减固定金额）</option>
        <option value="percent">折扣（按比例打折）</option>
      </select>
      <label class="fl">{{ f.type === "fixed" ? "面额（元）" : "折扣（如 9 折填 90）" }}</label>
      <input v-model.number="valueYuan" type="number" min="1" placeholder="如：10">
      <label class="fl">使用门槛（满多少元可用，0 = 无门槛）</label>
      <input v-model.number="minSpendYuan" type="number" min="0" placeholder="如：0">
      <label class="fl">发行量（张）</label>
      <input v-model.number="f.total_quantity" type="number" min="1" max="100000" placeholder="如：100">
      <label class="fl">每人限领（张）</label>
      <input v-model.number="f.per_user_limit" type="number" min="1" max="20">
      <label class="fl">有效期（起 / 止）</label>
      <div class="cap-row">
        <input v-model="f.valid_from" type="date">
        <input v-model="f.valid_to" type="date">
      </div>
      <div class="err-box" v-if="err">{{ err }}</div>
      <div class="ok-box" v-if="ok">${ICONS.check} {{ ok }}</div>
      <button class="big-cta" @click="create" :disabled="busy" style="margin-top:14px">
        {{ busy ? "创建中…" : "创建券模板" }}</button>
    </div>
    <div class="sec-card glass">
      <div class="sec-t">已有券模板<span>共 {{ list.length }} 个</span></div>
      <div class="sec-row" v-for="t in list" :key="t.id">
        <div style="flex:1">
          <div class="tt">${ICONS.ticket} {{ t.name }}
            <span class="tag" :class="t.status === 'active' ? 'ok' : 'cancel'">
              {{ t.status === "active" ? "发放中" : "已停发" }}</span></div>
          <div class="sub">{{ ruleText(t) }} · 已领 {{ t.claimed }}/{{ t.total_quantity }} ·
            剩 {{ t.remaining }} · 至 {{ (t.valid_to || "").slice(0, 10) }}</div>
        </div>
        <button class="bk-btn line" v-if="t.status === 'active'" @click="stop(t)">停发</button>
      </div>
      <div class="empty" v-if="!loading && !list.length">${ICONS.ticket}还没有券模板，用上方表单创建</div>
    </div>
  </div>`,
  data: () => ({ list: [], loading: true,
                f: { name: "", type: "fixed", total_quantity: 100, per_user_limit: 1,
                     valid_from: "", valid_to: "" },
                err: "", ok: "", busy: false }),
  computed: {
    valueYuan: {
      get() { return (this.f.type === "percent" ? this.f.value / 100 : this.f.value / 100) || undefined; },
      set(v) {
        const n = Number(v) || 0;
        this.f.value = this.f.type === "percent" ? Math.round(n * 100) : Math.round(n * 100);
      },
    },
    minSpendYuan: {
      get() { return this.f.min_spend_cents / 100 || 0; },
      set(v) { this.f.min_spend_cents = Math.round((Number(v) || 0) * 100); },
    },
  },
  async mounted() {
    const now = new Date();
    this.f.valid_from = now.toISOString().slice(0, 10);
    this.f.valid_to = new Date(now.getTime() + 90 * 86400000).toISOString().slice(0, 10);
    await this.load();
  },
  methods: {
    async load() {
      this.list = (await API.fetch("/api/admin/coupon-templates")).items;
      this.loading = false;
    },
    ruleText(t) {
      const val = t.type === "fixed" ? `立减 ¥${(t.value / 100).toFixed(0)}` : `享 ${(t.value / 100).toFixed(1)} 折`;
      return t.min_spend_cents > 0 ? `满 ¥${(t.min_spend_cents / 100).toFixed(0)} ${val}` : val;
    },
    async create() {
      this.err = ""; this.ok = "";
      if (!this.f.name) { this.err = "请填写券名"; return; }
      if (!this.f.value || this.f.value <= 0) { this.err = "请填写面额/折扣"; return; }
      this.busy = true;
      try {
        const iso = d => `${d}T00:00:00`;
        await API.fetch("/api/admin/coupons", { method: "POST", body: JSON.stringify({
          ...this.f, min_spend_cents: this.f.min_spend_cents || 0,
          valid_from: iso(this.f.valid_from), valid_to: iso(this.f.valid_to) })});
        this.ok = `已创建「${this.f.name}」，用户可在领券中心领取`;
        this.f.name = "";
        await this.load();
      } catch (e) { this.err = e.message; }
      finally { this.busy = false; }
    },
    async stop(t) {
      if (!(await this.$root.confirm(`停发「${t.name}」后用户将不能再领取，已领取的仍可使用。确认停发？`, "停发券模板", "停发"))) return;
      try {
        await API.fetch(`/api/admin/coupons/${t.id}/status`, { method: "PATCH",
          body: JSON.stringify({ status: "inactive" })});
        await this.load();
      } catch (e) { this.err = e.message; }
    },
  },
};
