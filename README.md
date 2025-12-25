# 🚀 Xpccm - 网站监控系统

一个轻量级、美观的网站监控系统，支持HTTP/HTTPS监控、SSL证书监控、多种通知渠道。

![预览](https://img.shields.io/badge/Python-3.8+-blue) ![License](https://img.shields.io/badge/License-MIT-green)

## ✨ 功能特点

- 📡 **多种监控类型**：HTTP/HTTPS、SSL证书、TCP端口、MySQL、Redis
- 🔔 **多种通知渠道**：Webhook、邮件、企业微信、Telegram、Bark、PushPlus、Server酱
- 🎨 **精美界面**：深色/浅色主题切换，响应式设计
- 📊 **数据可视化**：实时状态图表、可用率统计、响应时间趋势
- 🔐 **后台管理**：安全的管理员认证系统
- 💾 **轻量存储**：SQLite数据库，无需额外依赖



<img width="1718" height="1304" alt="image" src="https://github.com/user-attachments/assets/58bc6d5c-aca5-425e-9d23-ff9b514a3a7d" />


<img width="1476" height="1209" alt="image" src="https://github.com/user-attachments/assets/ddbe5fee-6e29-4dc1-98d6-0f3310c14cfc" />







## 🐳 Docker 一键部署（推荐）

```bash
# 克隆项目
git clone https://github.com/你的用户名/site-monitor.git
cd site-monitor

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

访问 http://localhost:5000 即可使用。

### Docker 相关命令

```bash
# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 更新版本
git pull
docker-compose up -d --build
```

## 📦 手动部署

### 环境要求

- Python 3.8+
- pip

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/你的用户名/site-monitor.git
cd site-monitor

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
python app.py
```

### 生产环境部署（推荐使用 Gunicorn）

```bash
# 安装 gunicorn
pip install gunicorn

# 启动服务
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## 🔧 配置说明

### 首次使用

1. 访问 http://localhost:5000/admin
2. 设置管理员用户名和密码（至少6位）
3. 登录后即可添加监控和配置通知渠道

### 网站设置

在后台管理 → 网站设置中可以配置：
- 网站标题和图标
- 页脚作者信息
- 备案号和链接

### 通知渠道配置

支持以下通知渠道：

| 渠道 | 配置示例 |
|-----|---------|
| Webhook | `{"url": "https://your-webhook.com"}` |
| 邮件 | `{"smtp_host": "smtp.qq.com", "smtp_port": 465, ...}` |
| 企业微信 | `{"webhook_url": "https://qyapi.weixin.qq.com/..."}` |
| Telegram | `{"bot_token": "xxx", "chat_id": "xxx"}` |

## 📁 项目结构

```
site-monitor/
├── app.py              # Flask主应用
├── database.py         # 数据库操作
├── monitor.py          # 监控检查器
├── notify.py           # 通知发送器
├── requirements.txt    # Python依赖
├── Dockerfile          # Docker构建文件
├── docker-compose.yml  # Docker编排文件
└── static/
    ├── index.html      # 前台页面
    └── admin.html      # 后台管理页面
```

## 🔐 安全说明

- 管理员密码使用SHA256哈希存储
- 所有写操作API需要登录认证
- 建议在生产环境配置HTTPS

## 📝 开源协议

MIT License

## 🙏 致谢

- [Flask](https://flask.palletsprojects.com/)
- [APScheduler](https://apscheduler.readthedocs.io/)
