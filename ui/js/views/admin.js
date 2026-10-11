/* 场馆管理首页：场馆列表（放场/编辑/休息/预约查询）+ 新建场馆 */
window.VIEWS = window.VIEWS || {};
VIEWS.admin = {
  template: `
  <div class="page">
    <div class="nav">
      <div class="back" @click="$back">${ICONS.back}</div>
      <div class="t"><div class="tt">场馆管理</div><div class="ts">选择场馆进行操作，或新建场馆</div></div>
    </div>
    <div class="sec-card glass" v-for="v in venues" :key="v.id">
      <div class="sec-t">{{ v.name }}<span class="tag ok" v-if="v.status === 'active'">营业中</span></div>
      <div class="muted" style="margin:2px 0 6px">${ICONS.pin}{{ v.address || "未填地址" }} ·
        营业 {{ v.open_time }}–{{ v.close_time }} · {{ v.slot_minutes }} 分钟/段 · {{ v.court_count }} 块场地</div>
      <div class="muted" v-if="v.breaks.length">休息：{{ v.breaks.map(b => b.start + "–" + b.end).join("、") }}</div>
      <div class="muted" v-if="v.closure_count">已设休息日 {{ v.closure_count }} 天 · 放场 {{ v.release_count }} 批</div>
      <div class="bk-btns" style="margin-top:10px;flex-wrap:wrap">
        <button class="bk-btn solid" @click="$go('#/mvenue/' + v.id + '/release')">放场</button>
        <button class="bk-btn line" @click="$go('#/mvenue/' + v.id + '/edit')">编辑</button>
        <button class="bk-btn line" @click="$go('#/mvenue/' + v.id + '/closure')">休息日</button>
        <button class="bk-btn line" @click="$go('#/mvenue/' + v.id + '/bookings')">预约查询</button>
      </div>
    </div>
    <div class="sec-card glass new-venue" @click="$go('#/mvenue/new')">
      <div class="sec-t" style="margin:0;color:var(--pri-d)">${ICONS.gift} 新建场馆</div>
      <div class="muted" style="margin-top:4px">配置营业时间、休息窗口、预约粒度与场地，点击放场生成预约表</div>
    </div>
    <div class="empty" v-if="!loading && !venues.length">${ICONS.pin}还没有场馆，点上方新建</div>
  </div>`,
  data: () => ({ venues: [], loading: true }),
  async mounted() {
    try { this.venues = (await API.fetch("/api/admin/venues")).items; }
    finally { this.loading = false; }
  },
};
