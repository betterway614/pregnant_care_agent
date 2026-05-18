# 移动端孕妇智能体 UI/UX 优化方案

基于 `ui-ux-pro-max` Skill 针对医疗、母婴（Maternal & Wellness）及移动端 App 的最佳实践，对 `frontend/src/views/pregnant/` 目录下的孕妇端界面制定以下深度优化方案。

## 核心设计系统 (Design System)

### 1. 设计风格 (Style)
*   **名称**: Accessible & Ethical + Soft UI (无障碍与柔和设计)
*   **关键词**: Soft, rounded, warm, gentle, high contrast, large text (16px+), 44x44px touch targets.
*   **适用场景**: 母婴、健康追踪、轻量级互动、无障碍环境。

### 2. 色彩规范 (Color Palette)
摒弃当前高饱和度或随意搭配的颜色（如纯深紫、生硬的橙色边框），采用专业且有温度的母婴医疗色系：
*   **主色调 (Primary)**: 温和粉/蜜桃色 (如 `#FB7185` / Rose 400) —— 传递母性、温暖与关怀。
*   **辅色调 (Secondary)**: 宁静蓝 (如 `#38BDF8` / Sky 400) —— 用于健康数据、医疗建议，传递专业与平静。
*   **背景色 (Background)**: 暖白/浅灰 (如 `#F8FAFC` 或 `#FFFBFB`) —— 减少视觉疲劳。
*   **文本色 (Text)**: 采用 `#1E293B` (Slate 800) 作为主标题，`#475569` (Slate 600) 作为次要文本，确保满足 WCAG 4.5:1 的对比度要求。
*   **反模式 (Anti-patterns)**: 避免使用明亮的霓虹色或 AI 感过强的深紫/粉色渐变。

### 3. 排版体系 (Typography)
*   **英文字体**: Heading 推荐 `Varela Round`，Body 推荐 `Nunito Sans`（柔和、圆润，非常适合母婴产品）。中文字体可统一使用 `PingFang SC` 或系统默认无衬线圆体。
*   **字号规范**: 移动端正文最小字号不低于 `14px`（推荐 `16px`），行高保持在 `1.5 - 1.75` 之间以提升可读性。

---

## 优先级 UI/UX 改造点 (按 Priority 排序)

### 优先级 1：无障碍与可用性 (Accessibility - CRITICAL)
*   **触控区域标准**: 当前移动端下的 `tool-item__icon` 尺寸为 `38x38px`，不符合苹果及安卓的移动端触控标准。**必须将所有可点击元素（包括返回按钮、工具网格、折叠面板头部）的最小触控区域提升至 `44x44px`**。
*   **对比度审查**: 确保浅色模式下的浅色渐变卡片（如 `bg-white/70`）上的文字依然有足够对比度。

### 优先级 2：视觉图标规范 (Icons - CRITICAL)
*   **移除 Emoji 图标**: 当前代码中大量使用了 Emoji（如 🍎, 👶, 🔔, 📋, 🫀, ⚖️ 等）。**UI-UX-Pro-Max 强烈指出这是不专业的反模式 (Anti-pattern)**。
*   **替换方案**: 全面改用高质量 SVG 图标库（如 `Lucide Icons` 或项目已内置的 `Element Plus Icons`）。宝宝大小可以采用专属绘制的精美插图或更扁平化的 SVG 图标替代 Emoji 水果。

### 优先级 3：交互与反馈 (Touch & Interaction - HIGH)
*   **点击反馈**: 确保所有 Card 和 Button 在 Hover (Web) 和 Active (移动端点击) 时有平滑过渡（`150ms-300ms`）。当前部分卡片缺少点击态反馈。
*   **光标规范**: 确保带有 `@click` 的元素全部添加 `cursor: pointer;`。
*   **骨架屏加载 (Loading States)**: 当前使用 `<Loading />` 图标，在移动端体验较为生硬。建议替换为内容骨架屏（Skeleton screens），保持布局不跳动 (Content jumping)。

---

## 具体组件优化建议 (针对 `PregnantHome.vue`)

1.  **顶部问候卡片 (Patient Header Card)**:
    *   移除当前的 Emoji 元素。将 "宝宝像一颗🍉大小" 设计为更有质感的图文模块，加入柔和的阴影 (`Soft box-shadow`)。
    *   渐变色可优化为 `linear-gradient(135deg, #FFF1F2 0%, #FCE7F3 100%)` 等更柔和的色值。
2.  **通知与提醒卡片 (FollowUp & Orders)**:
    *   随访卡片的 "心跳点" (`pulse-dot`) 动画是一个很好的 UX，但需要配合柔和的卡片背景，避免过重的边框线。
    *   医嘱卡片的 `border-left: 4px solid #e6a23c;` 过于生硬（企业后台风格），在移动端可以改为带柔和背景色的 Badge 或图标提示。
3.  **健康趋势与数据展示 (Health Trends)**:
    *   取消表情符号（🫀、🩸），改用如 `<Heart />` 等规范的 SVG 图标。
    *   数据突出的数值部分建议使用 `Nunito Sans` 等更柔和的数字字体。异常状态 (`trend-item--warning`) 的橙色/红色背景应确保不刺眼。
4.  **孕期助手工具区 (Tool Grid)**:
    *   当前是 `flex` 或 `grid` 布局。调整内外边距，确保图标周围有足够的留白。统一所有工具卡片的圆角（如 `12px - 16px`）。

## 开发实施路径 (Next Steps)
1.  **引入统一 Design Token**: 在 CSS 中定义主色、辅色、中性色变量，替换代码中散落的 Hex 颜色值（如 `#42A5F5`, `#CE93D8` 等）。
2.  **重构图标库**: 扫描并移除 `PregnantHome.vue`、`PregnantTools.vue` 等文件中的 emoji，引入或复用组件库的标准化 SVG。
3.  **标准化卡片组件**: 提取通用的 `SoftCard` 组件，统一阴影、边距、圆角和点击交互，减少重复的 `linear-gradient` 写法。
4.  **移动端适配调试**: 按照规范在 375px 和 430px 设备下验证触控目标大小和字体可读性。