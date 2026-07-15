# Online Python Editor

An interactive web application for teaching and learning Python programming, with automatic code evaluation and comprehensive teacher management features.

<br />

## 项目简介 / Project Overview

在线Python编辑器是一个面向中学编程教学的Web应用，提供教师和学生两种角色的完整功能。

The Online Python Editor is a web application designed for secondary school programming education, providing comprehensive features for both teachers and students.

### 主要功能 / Key Features

#### 教师功能 / Teacher Features

- **题库管理** - 创建、编辑、删除编程题目，支持今日题目设置
- **答题统计** - 查看学生答题情况，支持按班级、分类筛选
- **代码查看** - 查看学生提交的代码，支持通过代码高亮显示
- **管理员控制** - 注册开关、数据清理、手动注册学生账号
- **教师账号管理** - 通过命令行脚本管理教师账号

#### 学生功能 / Student Features

- **在线编程** - 实时编写和运行Python代码
- **答题系统** - 完成指定编程题目，查看通过状态
- **今日题目** - 查看当日推荐练习题目
- **代码保存** - 自动保存答题记录和通过代码

### 技术特性 / Technical Features

- 安全的代码沙箱执行环境
- SQLite数据库存储
- Bootstrap 5响应式界面
- 代码语法高亮
- 支持`input()`交互输入
- **AI代码评审** - 集成DeepSeek API提供智能代码分析和改进建议

## 安装与运行 / Installation & Run

### 环境要求 / Requirements

- Python 3.8+
- Windows / Linux / macOS

### 安装步骤 / Installation Steps

1. **克隆项目 / Clone the repository**
   ```bash
   git clone https://github.com/pcseal/online-python-editor.git
   cd online-python-editor
   ```
2. **创建虚拟环境 / Create virtual environment**
   ```bash
   python -m venv .venv

   # Windows
   .venv\Scripts\activate

   # macOS/Linux
   source .venv/bin/activate
   ```
3. **安装依赖 / Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **启动应用 / Start the application**
   ```bash
   python app.py
   ```
5. **访问应用 / Access the application**
   - Open your browser and navigate to: <http://127.0.0.1:8082>

### Windows快捷启动 / Windows Quick Start
```bash
start.bat
```

### 环境变量配置 / Environment Variables

创建 `.env` 文件配置AI服务（可选）：

```env
# AI API Key（配置后启用AI代码评审功能）
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

# 或使用 OpenAI 兼容接口
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo

# Flask 密钥（用于会话管理）
FLASK_SECRET_KEY=dev_key_123
```

**AI功能说明**：
- 配置API Key后，学生可以使用"AI分析"功能获得代码评审和改进建议
- AI分析有30秒冷却时间，防止滥用
- 支持DeepSeek和OpenAI兼容接口
- 不配置API Key不影响系统核心功能

## 默认账号 / Default Accounts

### 教师账号 / Teacher Accounts

系统初始化时会自动创建10个教师账号：

| 用户名       | 密码              |
| --------- | --------------- |
| teacher1  | teacher1\@2024  |
| teacher2  | teacher2\@2024  |
| ...       | ...             |
| teacher10 | teacher10\@2024 |

### 学生注册 / Student Registration

学生可以通过注册页面自行注册账号，需选择年段和班级。

## 教师账号管理脚本 / Teacher Management Script

提供命令行脚本管理教师账号：

```bash
# 列出所有教师
python manage_teachers.py list

# 添加新教师
python manage_teachers.py add

# 修改教师信息
python manage_teachers.py modify

# 删除教师账号
python manage_teachers.py delete

# 显示帮助
python manage_teachers.py help
```

## 项目结构 / Project Structure

```
online-python-editor/
├── app.py              # Flask应用主入口
├── models.py           # 数据库模型和操作
├── code_execution.py   # 代码执行逻辑
├── code_sandbox.py     # 代码沙箱环境
├── manage_teachers.py  # 教师账号管理脚本
├── requirements.txt    # Python依赖
├── start.bat           # Windows启动脚本
├── static/             # 静态资源
│   ├── logo.jpg
│   └── style.css
└── templates/          # HTML模板
    ├── login.html      # 登录页面
    ├── register.html   # 注册页面
    ├── sandbox.html    # Python沙箱页面
    ├── student/        # 学生端页面
    └── teacher/        # 教师端页面
```

## 使用说明 / Usage

### 教师使用流程 / Teacher Workflow

1. 登录教师账号
2. 在"题库管理"中创建或编辑题目
3. 设置"今日题目"供学生练习
4. 在"答题统计"中查看学生答题情况
5. 使用"管理员控制"管理系统配置

### 学生使用流程 / Student Workflow

1. 注册并登录学生账号
2. 在"今日题目"中查看当天练习
3. 在答题页面编写并运行代码
4. 通过题目后系统自动保存代码

## 配置说明 / Configuration

### 数据库 / Database

项目使用SQLite数据库，数据库文件位于 `database.db`。

首次启动时会自动创建数据库表和示例数据。

### 注册开关 / Registration Toggle

管理员可以通过"管理员控制"页面开启或关闭学生注册功能。

## 技术栈 / Tech Stack

- **后端**: Python 3, Flask
- **前端**: HTML5, CSS3, JavaScript, Bootstrap 5
- **数据库**: SQLite 3
- **代码编辑器**: Ace Editor
- **图标**: Bootstrap Icons

## 许可证 / License

MIT License

## 贡献 / Contributing

欢迎提交Issue和Pull Request！

## 联系方式 / Contact

项目地址: <https://github.com/pcseal/online-python-editor>
