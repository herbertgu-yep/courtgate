window.VIEWS = window.VIEWS || {};
VIEWS.login = {
  template: `
  <div class="page">
    <div class="brand">
      <div class="logo">Court<span>Gate</span></div>
      <p>场馆场地分时预约</p>
    </div>
    <div class="form-card glass">
      <label class="fl">账号</label>
      <input v-model="username" maxlength="20" autocomplete="username" placeholder="用户名" @keyup.enter="doLogin">
      <label class="fl">密码</label>
      <div class="cap-row">
        <input v-model="password" :type="showPwd ? 'text' : 'password'" autocomplete="current-password"
               placeholder="密码" @keyup.enter="doLogin">
        <button class="bk-btn line" @click="showPwd = !showPwd">{{ showPwd ? "隐藏" : "显示" }}</button>
      </div>
      <label class="fl">图形验证码（不区分大小写，看不清点击图片刷新）</label>
      <div class="cap-row">
        <input v-model="captchaCode" maxlength="4" placeholder="4 位验证码" style="text-transform:uppercase">
        <img :src="captchaImg" alt="验证码" title="看不清？点击刷新" @click="refreshCaptcha">
      </div>
      <div class="err-box" v-if="err">{{ err }}</div>
      <button class="big-cta" @click="doLogin" :disabled="busy" style="margin-top:14px">
        {{ busy ? "登录中…" : "登录" }}</button>
      <div class="auth-foot">没有账号？<a href="#/register">去注册</a></div>
    </div>
  </div>`,
  data: () => ({ username: "", password: "", showPwd: false, captchaCode: "", captchaId: "", captchaImg: "",
                 err: "", busy: false }),
  async mounted() { await this.refreshCaptcha(); },
  methods: {
    async refreshCaptcha() {
      const cap = await API.fetch("/api/auth/captcha");
      this.captchaId = cap.captcha_id;
      this.captchaImg = cap.image;
      this.captchaCode = "";
    },
    validate() {
      if (!this.username) { this.err = "请输入账号"; return false; }
      if (!this.password) { this.err = "请输入密码"; return false; }
      if (this.captchaCode.length !== 4) { this.err = "请输入 4 位图形验证码"; return false; }
      return true;
    },
    async doLogin() {
      if (!this.validate()) return;
      this.busy = true; this.err = "";
      try {
        const r = await API.fetch("/api/auth/login", {
          method: "POST", body: JSON.stringify({
            username: this.username.trim(), password: this.password,
            captcha_id: this.captchaId, captcha_code: this.captchaCode })});
        this.$root.afterAuth(r);
      } catch (e) { this.err = e.message; await this.refreshCaptcha(); }
      finally { this.busy = false; }
    },
  },
};
