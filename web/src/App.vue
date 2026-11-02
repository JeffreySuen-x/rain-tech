<script setup>
import BrandMark from './BrandMark.js'
import { ref, onMounted, onBeforeUnmount } from 'vue'
import AgricultureWorkbench from './agriculture/AgricultureWorkbench.vue'
import { useWorkspace } from './store.js'
const s = useWorkspace(), username = ref(''), password = ref('')
let timer
async function login() { await s.login(username.value, password.value); password.value = '' }
onMounted(() => { s.initialize(); timer = setInterval(() => s.poll(), 1500) })
onBeforeUnmount(() => clearInterval(timer))
</script>
<template>
  <div v-if="s.booting" class="boot" role="status"><BrandMark class="agri-auth-drop" /><p>正在打开工作台…</p></div>
  <main v-else-if="!s.user" class="auth-layout">
    <section class="auth-story"><a href="#login" class="brand"><BrandMark class="agri-auth-drop" /><span>澍雨<small>农业助手</small></span></a><div class="auth-intro"><p class="eyebrow">澍雨 · 农业助手</p><h1>看清园里的变化，<br>把下一步落到实处。</h1><p>把地块、现场照片和监测记录放在一起，<br>从发现变化，到核实、处理与跟进。</p><span class="waterline" aria-hidden="true"></span></div><footer>现场有记录 · 行动有依据</footer></section>
    <section class="auth-form" id="login"><div class="mobile-auth-welcome"><img src="/brand/shuyu-raindrop-v1.png" alt="澍雨"><h1>欢迎使用澍雨</h1><p>把现场看清楚，把农事记下来</p></div><p class="eyebrow">欢迎回来</p><h2>登录农业工作台</h2><p class="muted">使用你的澍雨账户，继续园区里的工作。</p><form @submit.prevent="login"><label>用户名<input v-model="username" name="username" autocomplete="username" required maxlength="100" autofocus></label><label>密码<input v-model="password" name="password" type="password" autocomplete="current-password" required></label><p v-if="s.error" class="error" role="alert">{{ s.error }}</p><button class="primary full" :disabled="s.busy">{{ s.busy ? '正在登录…' : '进入工作台' }} <span aria-hidden="true">→</span></button></form><p class="auth-foot">资料与任务保存在你部署的服务器上。</p></section>
  </main>
  <AgricultureWorkbench v-else />
</template>

<style scoped>
.agri-auth-drop{width:72px;height:72px;object-fit:contain;flex-shrink:0}.auth-story{background:radial-gradient(ellipse at 20% 80%,#49634c99,transparent 70%),#213f35;color:#f2f6ee}.auth-story .brand{font-family:Arial,'PingFang SC',sans-serif;letter-spacing:0;font-weight:700;gap:14px}.auth-story .brand small{color:#c0d3c2;letter-spacing:0;font-size:13px;font-weight:400}.auth-intro .eyebrow{color:#bdd5c3}.auth-intro h1{font-family:Arial,'PingFang SC',sans-serif;line-height:1.7;font-weight:600;letter-spacing:0}.auth-intro>p:not(.eyebrow){color:#c2d0c6}.auth-story footer{color:#bdd0c1}.auth-story:after{border-color:#a1c39a22;box-shadow:0 0 0 30px #8ca98108,0 0 0 70px #8ca98107}.waterline{border-color:#74a38a}.auth-form h2{font-family:Arial,'PingFang SC',sans-serif;font-weight:700;color:#203d2d}.auth-form .eyebrow{color:#4a765b}.auth-form .primary{background:#2e5943;border-color:#2e5943}.auth-form .primary:hover{background:#214734}.boot{background:#f8faf5}

.mobile-auth-welcome{display:none}@media(max-width:767px){.auth-layout{display:block;min-height:100dvh;background:#fff url('/friendly/covers-grid-v1.png') center bottom/100% 180px no-repeat;padding:0 0 190px}.auth-story{display:none}.auth-form{padding:30px 22px 0;max-width:440px;margin:auto;background:transparent;box-sizing:border-box}.auth-form>.eyebrow,.auth-form>h2,.auth-form>.muted{display:none}.mobile-auth-welcome{display:block;text-align:center;margin-bottom:30px}.mobile-auth-welcome img{width:150px;height:165px;object-fit:contain}.mobile-auth-welcome h1{font-size:28px;color:#103d33;margin:10px 0}.mobile-auth-welcome p{font-size:16px;color:#69756e;margin:8px 0}.auth-form form{gap:14px}.auth-form input{box-sizing:border-box;min-height:53px;border-radius:12px;font-size:17px;width:100%}.auth-form .primary{min-height:54px;background:#165442;border-radius:12px;font-size:18px;margin-top:10px}.auth-foot{text-align:center;font-size:13px}.auth-form label{font-size:14px}}
</style>
