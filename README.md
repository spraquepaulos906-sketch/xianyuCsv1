# 🚀 xianyuCsv1 - 智能闲鱼客服机器人系统

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/) [![LLM Powered](https://img.shields.io/badge/LLM-powered-FF6F61)](https://platform.openai.com/)

专为闲鱼平台打造的AI值守解决方案，实现闲鱼平台7×24小时自动化值守，支持多专家协同决策、智能议价和上下文感知对话。

## 🌟 核心特性

### 智能对话引擎
| 功能模块   | 技术实现            | 关键特性                                                     |
| ---------- | ------------------- | ------------------------------------------------------------ |
| 上下文感知 | 会话历史存储        | 轻量级对话记忆管理，完整对话历史作为LLM上下文输入            |
| 专家路由   | LLM prompt+规则路由 | 基于提示工程的意图识别 → 专家Agent动态分发，支持议价/技术/客服多场景切换 |

### 业务功能矩阵
| 模块     | 已实现                        | 规划中                       |
| -------- | ----------------------------- | ---------------------------- |
| 核心引擎 | ✅ LLM自动回复<br>✅ 上下文管理 | 🔄 情感分析增强               |
| 议价系统 | ✅ 阶梯降价策略                | 🔄 市场比价功能               |
| 技术支持 | ✅ 网络搜索整合                | 🔄 RAG知识库增强              |
| 运维监控 | ✅ 基础日志<br>✅ Web管理界面  | 🔄 钉钉集成                  |

## 🎨 效果图
<div align="center">
  <img src="./images/demo1.png" width="600" alt="客服">
  <br>
  <em>图1: 客服随叫随到</em>
</div>

<div align="center">
  <img src="./images/demo2.png" width="600" alt="议价专家">
  <br>
  <em>图2: 阶梯式议价</em>
</div>

<div align="center">
  <img src="./images/demo3.png" width="600" alt="技术专家">
  <br>
  <em>图3: 技术专家上场</em>
</div>

<div align="center">
  <img src="./images/log.png" width="600" alt="后台log">
  <br>
  <em>图4: 后台log</em>
</div>

## 🚴 快速开始

### 环境要求
- Python 3.8+

### 安装步骤
```bash
# 1. 克隆仓库
git clone https://github.com/spraquepaulos906-sketch/xianyuCsv1.git
cd xianyuCsv1

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置模型（LLM）
#    复制 config.example.json 为 config.json，填入你的 API Key：
#    - base_url：模型服务地址，如 https://api.deepseek.com/v1
#    - model_name：模型名，如 deepseek-chat
#    支持多模型，可在 Web 控制台内增删改查与切换当前模型。

# 4. 配置闲鱼 Cookie
#    复制 .env.example 为 .env，填入 COOKIES_STR（网页端获取，见下方说明）
```

获取闲鱼 Cookie：网页端登录闲鱼后，F12 打开控制台 → Network → Fetch/XHR → 点击任意请求 → 查看请求头中的 cookies，填入 `.env` 的 `COOKIES_STR`。

`.env` 中的可选配置：
- `TOGGLE_KEYWORDS`：接管模式切换关键词，默认句号（输入句号切换人工接管，再次输入切回 AI 接管）
- `SIMULATE_HUMAN_TYPING`：是否模拟人工回复延迟（True/False）

### 使用方法

运行主程序：
```bash
python main.py
```
启动后访问 http://127.0.0.1:8000 打开 Web 控制台。

### 自定义提示词

可以通过编辑 `prompts` 目录下的文件来自定义各个专家的提示词：

- `classify_prompt.txt`: 意图分类提示词
- `price_prompt.txt`: 价格专家提示词
- `tech_prompt.txt`: 技术专家提示词
- `default_prompt.txt`: 默认回复提示词

## 🤝 参与贡献

欢迎通过 Issue 提交建议或 PR 贡献代码。

## 🛡 注意事项

⚠️ 本项目仅供学习与交流，如有侵权请联系作者删除。

## 👤 作者

- 作者：`spraquepaulos906-sketch`

## 📈 Star 趋势
<a href="https://www.star-history.com/#spraquepaulos906-sketch/xianyuCsv1&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=spraquepaulos906-sketch/xianyuCsv1&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=spraquepaulos906-sketch/xianyuCsv1&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=spraquepaulos906-sketch/xianyuCsv1&type=Date" />
 </picture>
</a>
