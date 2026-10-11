window.VIEWS = window.VIEWS || {};
VIEWS.register = {
  template: `
  <div class="page">
    <div class="brand">
      <div class="logo">Court<span>Gate</span></div>
      <p>注册账号</p>
    </div>
    <div class="form-card glass">
      <label class="fl">账号（4~20 位字母、数字或下划线）</label>
      <input v-model="username" maxlength="20" placeholder="用户名">
      <label class="fl">设置密码</label>
      <input v-model="password" type="password" placeholder="密码">
      <ul class="pwrules">
        <li v-for="r in rules" :key="r.text" :style="{ color: r.ok ? 'var(--pri-d)' : 'var(--mut)' }">
          {{ r.ok ? "✓" : "○" }} {{ r.text }}</li>
      </ul>
      <label class="fl">确认密码</label>
      <input v-model="password2" type="password" placeholder="再次输入密码">
      <label class="fl">图形验证码（不区分大小写，看不清点击图片刷新）</label>
      <div class="cap-row">
        <input v-model="captchaCode" maxlength="4" placeholder="4 位验证码" style="text-transform:uppercase">
        <img :src="captchaImg" alt="验证码" title="看不清？点击刷新" @click="refreshCaptcha">
      </div>
      <label class="fl">昵称（选填）</label>
      <input v-model="nickname" maxlength="20" placeholder="给自己起个名字">
      <div class="err-box" v-if="err">{{ err }}</div>
      <button class="big-cta" @click="submit" :disabled="busy || !allOk" style="margin-top:14px">
        {{ busy ? "注册中…" : "注册并登录" }}</button>
      <div class="auth-foot">已有账号？<a href="#/login">去登录</a></div>
    </div>
  </div>`,
  data: () => ({
    username: "", password: "", password2: "", nickname: "",
    captchaCode: "", captchaId: "", captchaImg: "", err: "", busy: false,
  }),
  computed: {
    rules() {
      return [
        { text: "至少 8 位", ok: this.password.length >= 8 },
        { text: "包含大写字母", ok: /[A-Z]/.test(this.password) },
        { text: "包含小写字母", ok: /[a-z]/.test(this.password) },
        { text: "包含数字", ok: /\d/.test(this.password) },
        { text: "包含特殊字符", ok: /[!@#$%^&*()_+\-=\[\]{};':",.<>/?\\|~]/.test(this.password) },
      ];
    },
    allOk() {
      return this.rules.every(r => r.ok)
          && this.username.length >= 4
          && this.password === this.password2
          && this.captchaCode.length === 4;
    },
  },
  async mounted() { await this.refreshCaptcha(); },
  methods: {
    async refreshCaptcha() {
      const cap = await API.fetch("/api/auth/captcha");
      this.captchaId = cap.captcha_id;
      this.captchaImg = cap.image;
      this.captchaCode = "";
    },
    validate() {
      if (this.username.length < 4) { this.err = "请输入至少 4 位账号"; return false; }
      if (!this.allOk) { this.err = "密码未满足全部规则"; return false; }
      return true;
    },
    async submit() {
      if (!this.validate()) return;
      this.busy = true; this.err = "";
      try {
        const r = await API.fetch("/api/auth/register", {
          method: "POST", body: JSON.stringify({
            username: this.username, password: this.password, nickname: this.nickname,
            captcha_id: this.captchaId, captcha_code: this.captchaCode })});
        this.$root.afterAuth(r);
      } catch (e) { this.err = e.message; await this.refreshCaptcha(); }
      finally { this.busy = false; }
    },
  },
};
