
1. 顶部导航栏模块
// 导航栏组件
const Navbar = () => {
  return (
    <div className="navbar">
      <button className="back-button">
        <i className="fas fa-chevron-left"></i>
      </button>
      <h1 className="title">孕期温暖陪伴</h1>
      <div className="actions">
        <button className="more-button">
          <i className="fas fa-ellipsis-h"></i>
        </button>
        <button className="settings-button">
          <i className="fas fa-cog"></i>
        </button>
      </div>
    </div>
  );
};
2. 用户信息模块
// 用户信息组件
const UserInfo = () => {
  return (
    <div className="user-info">
      <div className="user-name">张笑笑</div>
      <button className="switch-button">
        <i className="fas fa-sync-alt"></i> 切换
      </button>
      <div className="action-buttons">
        <button className="volume-button">
          <i className="fas fa-volume-mute"></i>
        </button>
        <button className="chat-button">
          <i className="fas fa-comment"></i>
        </button>
        <button className="menu-button">
          <i className="fas fa-bars"></i>
        </button>
      </div>
    </div>
  );
};
3. 欢迎信息模块
// 欢迎信息组件
const WelcomeSection = () => {
  return (
    <div className="welcome-section">
      <h2>您好，我是数智医生小溪</h2>
      <p>在这里，我将为您提供全方位的孕产知识支持，陪伴您度过一个安心、健康的孕期旅程~</p>
      <div className="doctor-avatar">
        <img src="doctor-avatar.png" alt="数智医生小溪" />
      </div>
    </div>
  );
};
4. 孕周指南模块
// 孕周指南组件
const PregnancyGuide = () => {
  return (
    <div className="pregnancy-guide">
      <h3 className="section-title">孕周指南</h3>
      <div className="week-info">
        <div className="week-number">孕6周3天</div>
        <div className="days-remaining">还有233天出生</div>
        <div className="fetus-image">
          <img src="fetus-icon.png" alt="胎儿" />
          <button className="click-me">点我</button>
        </div>
        <div className="measurements">
          <div className="measurement">
            <span>身长</span>
            <span>4-6mm</span>
          </div>
          <div className="measurement">
            <span>体重</span>
            <span>0.5-1g</span>
          </div>
        </div>
        <div className="pagination-dots">
          <div className="dot active"></div>
          <div className="dot"></div>
          <div className="dot"></div>
        </div>
      </div>
    </div>
  );
};
5. 兴趣推荐模块
// 兴趣推荐组件
const InterestRecommendations = () => {
  const interests = [
    { id: 1, title: "孕期营养有哪些推荐食物?" },
    { id: 2, title: "如何缓解孕吐?" },
    { id: 3, title: "孕期运动有哪些推荐?" }
  ];
  return (
    <div className="interests">
      <h3 className="section-title">您可能感兴趣：</h3>
      <div className="interest-list">
        {interests.map(interest => (
          <div key={interest.id} className="interest-item">
            <i className="fas fa-hashtag"></i>
            <span>{interest.title}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
6. 功能导航模块
// 功能导航组件
const FunctionNavigation = () => {
  const functions = [
    { id: 1, name: "深度思考", icon: "fas fa-brain", color: "pink" },
    { id: 2, name: "数胎动", icon: "fas fa-heartbeat", color: "orange" },
    { id: 3, name: "超声报告", icon: "fas fa-file-medical", color: "yellow" }
  ];
  return (
    <div className="function-nav">
      <div className="function-items">
        {functions.map(func => (
          <div key={func.id} className={`function-item ${func.color}`}>
            <i className={func.icon}></i>
            <span>{func.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
7. 底部输入模块
// 底部输入组件
const BottomInput = () => {
  return (
    <div className="bottom-input">
      <div className="input-area">
        <i className="fas fa-microphone"></i>
        <input 
          type="text" 
          placeholder="健康问题可以随时来问我哦~" 
          readOnly
        />
        <button className="refresh-button">
          <i className="fas fa-sync-alt"></i>
        </button>
      </div>
    </div>
  );
};
风格设计指南
色彩系统
:root {
  /* 主色调 - 温柔粉色系 */
  --primary-pink: #FFB6C1;      /* 浅粉 */
  --primary-light: #FFE4E1;     /* 极浅粉 */
  --primary-dark: #FF69B4;      /* 热粉 */
  /* 辅助色 */
  --secondary-white: #FFFFFF;   /* 白色 */
  --secondary-gray: #F5F5F5;    /* 浅灰 */
  --secondary-dark: #333333;    /* 深灰 */
  /* 强调色 */
  --accent-coral: #FF6B81;      /* 珊瑚红 */
  --accent-mint: #98D8C8;       /* 薄荷绿 */
  --accent-yellow: #FFD93D;     /* 阳光黄 */
}
/* 全局样式 */
body {
  background-color: var(--primary-light);
  font-family: 'PingFang SC', 'Helvetica Neue', Arial, sans-serif;
  margin: 0;
  padding: 0;
}
/* 卡片样式 */
.card {
  background: white;
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  margin: 16px;
}
/* 按钮样式 */
.button-primary {
  background: var(--accent-coral);
  color: white;
  border-radius: 20px;
  padding: 8px 16px;
  border: none;
  cursor: pointer;
  transition: all 0.3s ease;
}
.button-primary:hover {
  background: var(--primary-dark);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(255, 105, 180, 0.3);
}
字体系统
/* 字体层级 */
.font-h1 {
  font-size: 24px;
  font-weight: 600;
  color: var(--secondary-dark);
  margin-bottom: 16px;
}
.font-h2 {
  font-size: 20px;
  font-weight: 500;
  color: var(--secondary-dark);
  margin-bottom: 12px;
}
.font-body {
  font-size: 16px;
  font-weight: 400;
  color: var(--secondary-dark);
  line-height: 1.6;
}
.font-caption {
  font-size: 14px;
  font-weight: 400;
  color: #888888;
  margin-top: 8px;
}
布局系统
/* 响应式布局 */
.container {
  max-width: 600px;
  margin: 0 auto;
  padding: 16px;
}
/* 导航栏布局 */
.navbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}
/* 功能导航布局 */
.function-nav {
  display: flex;
  justify-content: space-around;
  padding: 16px;
  background: white;
  border-radius: 16px;
  margin: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}
.function-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
}
.function-item:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}
/* 底部输入布局 */
.bottom-input {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: white;
  padding: 16px;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.1);
}
.input-area {
  display: flex;
  align-items: center;
  background: var(--secondary-gray);
  border-radius: 24px;
  padding: 8px 16px;
}
交互设计
// 按钮交互效果
const buttons = document.querySelectorAll('.button-primary');
buttons.forEach(button => {
  button.addEventListener('click', function() {
    this.style.transform = 'scale(0.95)';
    setTimeout(() => {
      this.style.transform = 'scale(1)';
    }, 150);
  });
  button.addEventListener('mouseenter', function() {
    this.style.boxShadow = '0 4px 12px rgba(255, 105, 180, 0.3)';
  });
  button.addEventListener('mouseleave', function() {
    this.style.boxShadow = '0 2px 8px rgba(255, 105, 180, 0.2)';
  });
});
// 卡片悬停效果
const cards = document.querySelectorAll('.card');
cards.forEach(card => {
  card.addEventListener('mouseenter', function() {
    this.style.transform = 'translateY(-4px)';
  });
  card.addEventListener('mouseleave', function() {
    this.style.transform = 'translateY(0)';
  });
});
数据可视化
// 孕周进度条组件
function renderPregnancyProgress(week, totalWeeks = 40) {
  const progress = (week / totalWeeks) * 100;
  return `
    <div class="progress-container">
      <div class="progress-bar" style="width: ${progress}%"></div>
      <div class="progress-label">${week}周 / ${totalWeeks}周</div>
    </div>
  `;
}
// 胎儿发育可视化
function renderFetusDevelopment(week) {
  const size = Math.min(week * 2, 80); // 最大80px
  return `
    <div class="fetus-visual" style="width: ${size}px; height: ${size}px;">
      <img src="fetus-${week}.svg" alt="胎儿发育图">
    </div>
  `;
}
这个设计指南完全基于您提供的图片内容，涵盖了从功能模块到风格设计的完整前端工程实现方案，可以根据具体技术栈和项目需求进行调整和扩展。