<template>
  <div class="tools-layout">
    <!-- ==================== 动态光晕背景 ==================== -->
    <div class="halo-bg">
      <div class="halo-orb halo-orb-1"></div>
      <div class="halo-orb halo-orb-2"></div>
      <div class="halo-backdrop"></div>
    </div>
    
    <div class="content-wrapper">
      <router-view />
    </div>
  </div>
</template>

<style scoped>
/* ========== 全局变量 (Soft UI Colors) ========== */
.tools-layout {
  --c-rose: #FB7185;
  --c-rose-light: #FFF1F2;
  --c-sky: #38BDF8;
  --c-sky-light: #F0F9FF;
  --c-indigo: #818CF8;
  --c-emerald: #34D399;
  --c-amber: #FBBF24;
  --c-orange: #FB923C;
  --c-slate-800: #1E293B;
  --c-slate-600: #475569;
  --c-slate-400: #94A3B8;
  --c-bg: #F8FAFC;
  --card-shadow: 0 4px 16px rgba(148, 163, 184, 0.08);
  --card-shadow-hover: 0 8px 24px rgba(148, 163, 184, 0.12);
  
  background-color: var(--c-bg);
  min-height: 100vh;
  position: relative;
  overflow-x: hidden;
  font-family: 'Nunito Sans', 'PingFang SC', sans-serif;
  color: var(--c-slate-800);
}

.content-wrapper {
  position: relative;
  z-index: 1;
  height: 100%;
}

/* ==================== 动态光晕背景 (Halo) ==================== */
.halo-bg {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  overflow: hidden;
  z-index: 0;
  pointer-events: none;
}
.halo-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(40px);
  opacity: 0.85;
  animation: halo-float 20s infinite ease-in-out alternate;
}
.halo-orb-1 {
  top: -10%; left: -20%;
  width: 140vw; height: 140vw;
  background: radial-gradient(circle, #FECDD3 0%, transparent 70%);
}
.halo-orb-2 {
  top: 40%; right: -20%;
  width: 120vw; height: 120vw;
  background: radial-gradient(circle, #FCE7F3 0%, transparent 70%);
  animation-delay: -5s;
}
.halo-backdrop {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  backdrop-filter: blur(40px);
  -webkit-backdrop-filter: blur(40px);
}
@keyframes halo-float {
  0% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(15vw, 15vh) scale(1.1); }
  100% { transform: translate(-10vw, 10vh) scale(0.9); }
}
</style>
