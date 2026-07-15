"""
Flask 主应用入口 —— Python 在线编程教学平台

核心功能：
  - 用户注册/登录（学生/教师）
  - 在线代码沙箱
  - AI 代码评审
  - 题库管理（教师）
  - 答题统计（教师）
"""
import os
import sys
import time

# Windows 终端编码修复
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

# matplotlib 非交互模式
try:
    import matplotlib
    matplotlib.use('Agg')
except ImportError:
    pass

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests

# 导入数据库模型
import models

# 初始化数据库（确保所有表和视图都存在，无论使用何种方式启动）
models.init_db()

# ============================================================================
# 配置
# ============================================================================
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev_key_please_change')

# AI 配置
AI_API_KEY = os.getenv('DEEPSEEK_API_KEY', os.getenv('OPENAI_API_KEY', ''))
AI_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', os.getenv('OPENAI_BASE_URL', 'https://api.deepseek.com'))
AI_MODEL = os.getenv('DEEPSEEK_MODEL', os.getenv('OPENAI_MODEL', 'deepseek-v4-flash'))

# 限制配置
RUN_COOLDOWN = 5  # 代码运行冷却时间（秒）
AI_COOLDOWN = 30   # AI分析冷却时间（秒）

# 系统提示词
AI_SYSTEM_MESSAGE = """你是一位专业的 Python 编程教师。你的任务是分析学生提交的代码，提供详细的评审和改进建议。



请用中文回复，格式清晰，适合初学者理解。"""

# ============================================================================
# 会话管理
# ============================================================================
def get_current_user():
    """获取当前登录用户"""
    if 'user_id' in session:
        return models.get_user_by_id(session['user_id'])
    return None

def is_logged_in():
    """检查是否已登录"""
    return 'user_id' in session

def is_teacher():
    """检查是否为教师"""
    user = get_current_user()
    return user and user['role'] == 'teacher'

from functools import wraps

def login_required(f):
    """登录装饰器"""
    @wraps(f)
    def decorated_function_login(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function_login

def teacher_required(f):
    """教师权限装饰器"""
    @wraps(f)
    def decorated_function_teacher(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('login'))
        if not is_teacher():
            return '无权限访问此页面', 403
        return f(*args, **kwargs)
    return decorated_function_teacher

# ============================================================================
# 路由
# ============================================================================
@app.route('/')
def index():
    """首页"""
    if not is_logged_in():
        return redirect(url_for('login'))
    
    user = get_current_user()
    if user['role'] == 'teacher':
        return redirect(url_for('teacher_dashboard'))
    else:
        return redirect(url_for('student_dashboard'))

# ------------------------------
# 用户认证
# ------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if is_logged_in():
        return redirect(url_for('index'))
    
    error = ''
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = models.authenticate(username, password)
        if user:
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['name'] = user['name']
            session['username'] = user['username']
            return redirect(url_for('index'))
        else:
            error = '用户名或密码错误'
    
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """学生注册页面"""
    if is_logged_in():
        return redirect(url_for('index'))
    
    if not models.get_registration_enabled():
        return render_template('register.html', error='注册功能已关闭，请联系管理员')
    
    error = ''
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        name = request.form.get('name')
        grade = request.form.get('grade')
        class_number = request.form.get('class_number')
        
        # 验证
        if password != confirm_password:
            error = '两次密码不一致'
        elif len(password) < 6:
            error = '密码长度至少6位'
        elif not username or not name:
            error = '请填写完整信息'
        elif not grade or not class_number:
            error = '请选择年段和班级'
        else:
            # 获取或创建班级
            class_id = models.get_or_create_class(grade, class_number)
            # 创建学生
            user_id = models.add_student(username, password, name, class_id)
            if user_id:
                return redirect(url_for('login'))
            else:
                error = '用户名已存在'
    
    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    return redirect(url_for('login'))

# ------------------------------
# 教师页面
# ------------------------------
@app.route('/teacher/dashboard')
@teacher_required
def teacher_dashboard():
    """教师仪表盘"""
    today_problems = models.get_today_problems()
    categories = models.get_all_categories()
    
    # 获取每个类别的题目列表
    problems_by_category = {}
    for category in categories:
        problems_by_category[category] = models.get_problems_by_category(category)
    
    return render_template('teacher/dashboard.html', 
                          today_problems=today_problems, 
                          categories=categories,
                          problems_by_category=problems_by_category)

@app.route('/teacher/problems')
@teacher_required
def teacher_problems():
    """题库管理"""
    problems = models.get_all_problems()
    categories = models.get_all_categories()
    selected_category = request.args.get('category', '')
    
    if selected_category:
        problems = [p for p in problems if p['category'] == selected_category]
    
    return render_template('teacher/problems.html', problems=problems, categories=categories, selected_category=selected_category)

@app.route('/teacher/problem/add', methods=['GET', 'POST'])
@teacher_required
def add_problem():
    """添加题目"""
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category')
        new_category = request.form.get('new_category', '').strip()
        full_code = request.form.get('full_code')
        student_code = request.form.get('student_code')
        expected_output = request.form.get('expected_output')
        
        # 如果选择了新增类别，使用新类别的值
        if category == '新增类别':
            if not new_category:
                error = '请输入新类别名称'
            else:
                category = new_category
        elif not category:
            error = '请选择或输入类别'
        
        if 'error' not in locals() and all([title, description, category, full_code, student_code, expected_output]):
            problem_id = models.add_problem(title, description, category, full_code, student_code, expected_output)
            if problem_id:
                return redirect(url_for('teacher_problems'))
            else:
                error = '添加失败'
        elif 'error' not in locals():
            error = '请填写完整信息'
    else:
        error = ''
    
    categories = models.get_all_categories()
    return render_template('teacher/add_problem.html', error=error, categories=categories)

@app.route('/teacher/problem/edit/<int:problem_id>', methods=['GET', 'POST'])
@teacher_required
def edit_problem(problem_id):
    """编辑题目"""
    problem = models.get_problem_by_id(problem_id)
    if not problem:
        return '题目不存在', 404
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category')
        new_category = request.form.get('new_category', '').strip()
        full_code = request.form.get('full_code')
        student_code = request.form.get('student_code')
        expected_output = request.form.get('expected_output')
        
        # 如果选择了新增类别，使用新类别的值
        if category == '新增类别':
            if not new_category:
                error = '请输入新类别名称'
            else:
                category = new_category
        
        if 'error' not in locals() and all([title, description, category, full_code, student_code, expected_output]):
            success = models.update_problem(problem_id, title, description, category, full_code, student_code, expected_output)
            if success:
                return redirect(url_for('teacher_problems'))
            else:
                error = '更新失败'
        elif 'error' not in locals():
            error = '请填写完整信息'
    else:
        error = ''
    
    categories = models.get_all_categories()
    return render_template('teacher/edit_problem.html', problem=problem, error=error, categories=categories)

@app.route('/teacher/problem/delete/<int:problem_id>')
@teacher_required
def delete_problem(problem_id):
    """删除题目"""
    models.delete_problem(problem_id)
    return redirect(url_for('teacher_problems'))

@app.route('/api/set_today_problem', methods=['POST'])
@login_required
def api_set_today_problem():
    """API：设置单个题目是否为今日题目"""
    data = request.get_json()
    problem_id = data.get('problem_id')
    is_today = data.get('is_today', False)
    
    if not problem_id:
        return jsonify({'success': False, 'error': '缺少题目ID'})
    
    # 获取当前所有今日题目
    today_problems = models.get_today_problems()
    today_ids = [p['id'] for p in today_problems]
    
    if is_today:
        # 添加到今日题目
        if problem_id not in today_ids:
            today_ids.append(problem_id)
    else:
        # 从今日题目中移除
        if problem_id in today_ids:
            today_ids.remove(problem_id)
    
    # 更新今日题目
    models.set_today_problems(today_ids)
    
    return jsonify({'success': True})

@app.route('/api/set_today_problems', methods=['POST'])
@login_required
def api_set_today_problems():
    """API：批量设置今日题目"""
    data = request.get_json()
    problem_ids = data.get('problem_ids', [])
    
    if not isinstance(problem_ids, list) or len(problem_ids) == 0:
        return jsonify({'success': False, 'error': '请选择题目'})
    
    # 设置今日题目
    models.set_today_problems(problem_ids)
    
    return jsonify({'success': True})

@app.route('/teacher/stats')
@teacher_required
def teacher_stats():
    """答题数据统计"""
    # 获取筛选参数
    grade = request.args.get('grade', '')
    class_number = request.args.get('class_number', '')
    category = request.args.get('category', '')
    
    all_problems = models.get_all_problems()
    
    # 按分类筛选题目
    if category:
        all_problems = [p for p in all_problems if p['category'] == category]
    
    # 获取每个题目的统计数据（支持班级筛选）
    problem_stats = []
    for problem in all_problems:
        stats = models.get_problem_stats(problem['id'], grade=grade, class_number=class_number)
        problem_stats.append({
            'id': problem['id'],
            'title': problem['title'],
            'category': problem['category'],
            'is_today': problem['is_today'],
            'attempt_count': stats['total_students'],
            'pass_count': stats['passed_students'],
            'total_runs': stats['total_runs'],
            'total_ai_uses': stats['total_ai_uses']
        })
    
    # 按是否今日题目排序（今日题目置顶）
    problem_stats.sort(key=lambda x: -x['is_today'])
    
    # 计算总体统计数据
    overall_stats = {
        'total_students': models.get_total_students(),
        'total_problems': len(all_problems),
        'total_runs': sum(p['total_runs'] for p in problem_stats),
        'total_ai_uses': sum(p['total_ai_uses'] for p in problem_stats)
    }
    
    # 获取学生统计数据
    student_stats = models.get_all_student_overall_stats(grade=grade, class_number=class_number)
    
    # 获取所有分类用于筛选
    categories = models.get_all_categories()
    
    return render_template('teacher/stats.html', 
                          problem_stats=problem_stats,
                          overall_stats=overall_stats,
                          student_stats=student_stats,
                          grade=grade,
                          class_number=class_number,
                          category=category,
                          categories=categories)

@app.route('/teacher/stats/problem/<int:problem_id>')
@teacher_required
def problem_stats_detail(problem_id):
    """题目详细统计"""
    problem = models.get_problem_by_id(problem_id)
    if not problem:
        return '题目不存在', 404
    
    grade = request.args.get('grade', '')
    class_number = request.args.get('class_number', '')
    
    stats = models.get_problem_stats(problem_id, grade=grade, class_number=class_number)
    student_stats = models.get_all_student_stats(problem_id, grade=grade, class_number=class_number)
    
    grades = models.get_all_grades()
    class_numbers = models.get_all_class_numbers()
    
    return render_template('teacher/problem_stats.html', 
                          problem=problem, 
                          stats=stats, 
                          student_stats=student_stats,
                          grade=grade,
                          class_number=class_number,
                          grades=grades,
                          class_numbers=class_numbers)

@app.route('/teacher/stats/problem/<int:problem_id>/code/<int:user_id>')
@teacher_required
def view_student_code(problem_id, user_id):
    """查看学生通过的代码"""
    problem = models.get_problem_by_id(problem_id)
    if not problem:
        return '题目不存在', 404
    
    student = models.get_single_student_stats(problem_id, user_id)
    
    if not student or not student['ever_passed']:
        return '学生未通过该题目', 404
    
    return render_template('teacher/view_student_code.html',
                          problem=problem,
                          student_name=student['name'],
                          passed_code=student['passed_code'],
                          passed_at=student.get('passed_at', ''))

@app.route('/teacher/admin', methods=['GET', 'POST'])
@teacher_required
def admin_control():
    """管理员控制面板"""
    message = ''
    message_type = 'success'
    
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        if action == 'toggle_registration':
            current = models.get_registration_enabled()
            models.set_registration_enabled(not current)
            message = '注册功能已{}'.format('关闭' if current else '开放')
            message_type = 'success'
        
        elif action == 'manual_register':
            username = request.form.get('username', '')
            name = request.form.get('name', '')
            password = request.form.get('password', '')
            grade = request.form.get('grade', '')
            class_number = request.form.get('class_number', '')
            
            if not username or not name or not password or not grade or not class_number:
                message = '请填写完整信息'
                message_type = 'danger'
            elif len(password) < 6:
                message = '密码至少6位'
                message_type = 'danger'
            else:
                class_id = models.get_or_create_class(grade, class_number)
                user_id = models.add_student(username, password, name, class_id)
                if user_id:
                    message = f'学生 {name} 注册成功'
                    message_type = 'success'
                else:
                    message = '用户名已存在'
                    message_type = 'danger'
        
        elif action == 'delete_data':
            delete_scope = request.form.get('delete_scope', 'all')
            delete_content = request.form.get('delete_content', 'data')
            grade = request.form.get('grade', '')
            class_number = request.form.get('class_number', '')
            
            if delete_scope == 'class' and not grade:
                message = '按班级删除时必须选择年段'
                message_type = 'danger'
            else:
                if delete_content == 'data':
                    count = models.delete_student_data(grade, class_number)
                    message = f'已删除 {count} 名学生的答题数据'
                else:
                    count = models.delete_student_accounts(grade, class_number)
                    message = f'已删除 {count} 名学生的账号及所有数据'
                message_type = 'success'
    
    registration_enabled = models.get_registration_enabled()
    grades = models.get_all_grades()
    
    return render_template('teacher/admin_control.html',
                          registration_enabled=registration_enabled,
                          grades=grades,
                          message=message,
                          message_type=message_type)

# ------------------------------
# 学生页面
# ------------------------------
@app.route('/student/dashboard')
@login_required
def student_dashboard():
    """学生仪表盘（今日题目）"""
    user = get_current_user()
    if user['role'] == 'teacher':
        return redirect(url_for('teacher_dashboard'))
    
    today_problems = models.get_today_problems()
    user_stats = models.get_user_submission_stats(user['id'])
    
    return render_template('student/dashboard.html', today_problems=today_problems, user_stats=user_stats)

@app.route('/student/problems')
@login_required
def student_problems():
    """题库浏览"""
    user = get_current_user()
    if user['role'] == 'teacher':
        return redirect(url_for('teacher_dashboard'))
    
    problems = models.get_all_problems()
    categories = models.get_all_categories()
    selected_category = request.args.get('category', '')
    
    if selected_category:
        problems = [p for p in problems if p['category'] == selected_category]
    
    user_stats = models.get_user_submission_stats(user['id'])
    
    return render_template('student/problems.html', problems=problems, categories=categories, 
                           selected_category=selected_category, user_stats=user_stats)

@app.route('/student/problem/<int:problem_id>')
@login_required
def student_problem(problem_id):
    """题目详情（代码编辑）"""
    user = get_current_user()
    if user['role'] == 'teacher':
        return redirect(url_for('teacher_dashboard'))
    
    problem = models.get_problem_by_id(problem_id)
    if not problem:
        return '题目不存在', 404
    
    user_stats = models.get_user_submission_stats(user['id'], problem_id)
    
    return render_template('student/problem.html', problem=problem, user_stats=user_stats)

# ------------------------------
# 代码执行 API
# ------------------------------
from code_execution import execute_python_code, AsyncCodeExecutor

code_executor = AsyncCodeExecutor()

@app.route('/api/execute_code', methods=['POST'])
@login_required
def api_execute_code():
    """执行代码（同步）"""
    user_id = session['user_id']
    problem_id = request.json.get('problem_id')
    
    # 检查冷却时间
    last_run = session.get('last_run_time', 0)
    now = time.time()
    if now - last_run < RUN_COOLDOWN:
        return jsonify({'error': f'请等待 {int(RUN_COOLDOWN - (now - last_run))} 秒后再运行'})
    
    session['last_run_time'] = now
    
    code = request.json.get('code')
    
    # 获取题目信息（用于获取测试代码）
    problem = None
    if problem_id:
        problem = models.get_problem_by_id(problem_id)
    
    # 如果有测试代码，将学生代码和测试代码合并执行
    full_code = code
    if problem and problem.get('test_code'):
        full_code = code.rstrip() + '\n\n' + problem['test_code']
    
    result = execute_python_code(full_code)
    
    # 更新答题统计
    if problem_id and problem:
        # 比较输出结果（忽略空格和换行差异）
        actual_output = (result.get('output') or '').strip()
        expected_output = problem['expected_output'].strip()
        
        # 使用更宽松的比较：忽略首尾空白和换行符差异
        actual_lines = [line.strip() for line in actual_output.split('\n') if line.strip()]
        expected_lines = [line.strip() for line in expected_output.split('\n') if line.strip()]
        is_passed = 1 if actual_lines == expected_lines else 0
        
        models.add_submission(user_id, problem_id, code, result.get('output', ''), is_passed, run_count=1, ai_count=0)
        
        # 返回统计信息用于前端更新
        user_stats = models.get_user_submission_stats(user_id, problem_id)
        result['user_stats'] = user_stats
        result['is_passed'] = bool(is_passed)
    
    return jsonify(result)

@app.route('/api/evaluate_code', methods=['POST'])
@login_required
def api_evaluate_code():
    """AI 代码评审"""
    # 检查冷却时间
    last_ai = session.get('last_ai_time', 0)
    now = time.time()
    if now - last_ai < AI_COOLDOWN:
        return jsonify({'error': f'请等待 {int(AI_COOLDOWN - (now - last_ai))} 秒后再使用 AI 分析'})
    
    session['last_ai_time'] = now
    
    code = request.json.get('code', '')
    problem_id = request.json.get('problem_id')
    output = request.json.get('output', '')
    error = request.json.get('error', '')
    
    # 获取题目信息
    problem = None
    full_code = ''
    student_template = ''
    expected_output = ''
    if problem_id:
        problem = models.get_problem_by_id(problem_id)
        if problem:
            full_code = problem.get('full_code', '')
            student_template = problem.get('student_code', '')
            expected_output = problem.get('expected_output', '')
    
    if not AI_API_KEY:
        return jsonify({'error': '未配置 AI API Key'}), 500
    
    try:
        # 判断学生是否填写了内容
        # 比较学生代码和模板代码，看是否有实质性修改
        def has_student_code(student_code, template):
            """判断学生是否填写了内容"""
            # 去除空白后的比较
            clean_student = ''.join(student_code.split())
            clean_template = ''.join(template.split())
            if clean_student == clean_template:
                return False
            # 检查是否有实际代码（不是只有注释和空白）
            code_lines = [line.strip() for line in student_code.split('\n') if line.strip()]
            has_code = False
            for line in code_lines:
                if line and not line.startswith('#'):
                    has_code = True
                    break
            return has_code
        
        student_has_code = has_student_code(code, student_template)
        
        # 构建提示词
        if not student_has_code:
            # 学生还没填写任何内容，让学生先思考
            prompt = """
你是学生的编程老师，正在帮助一位基础薄弱的学生学习编程。

重要提醒：这是一次性的单向分析，学生无法回复你，只能看到你输出的文字。

题目描述：
{problem_desc}
请用简洁易懂的语言给学生一些解题提示。


注意：
1. 不要给出任何代码或直接答案
2. 可以提示这道题涉及的基本概念或算法思路
3. 分析要简短，适合基础薄弱的学生理解
4. 用鼓励的语气引导学生自己尝试
5. 直接给出提示内容，不要问学生"有什么想法"、"遇到什么困难"这类对话式问题

请直接输出你的提示内容：
""".format(problem_desc=problem.get('description', '这是一道编程练习题') if problem else '这是一道编程练习题')
        
        else:
            # 学生已经填写了部分代码，进行引导式分析（结合运行结果）
            prompt = """
你是一位耐心的编程老师，正在帮助基础薄弱的学生学习编程。

重要提醒：这是一次性的单向分析，学生无法回复你，只能看到你输出的文字。

请分析学生的代码及其运行结果，给出引导式的反馈。

题目完整代码（仅用于你的参考，不要告诉学生）：
```python
{full_code}
```

重要说明：学生代码中的 ①②③④⑤⑥⑦⑧⑨⑩ 等带圈数字符号是填空占位符，表示学生尚未填写的位置，不代表学生实际编写的代码。请据此理解学生的完成进度，针对已填写的部分进行分析。

学生的代码：
```python
{student_code}
```

代码运行结果：
输出:
{output}

错误信息:
{error}

预期输出:
{expected_output}

严格要求：
1. 🔒🔒🔒 绝对禁止给出任何代码、代码片段、代码示例或完整解决方案
2. 🔒🔒🔒 绝对禁止直接告诉学生答案或正确写法
3. 🔒🔒🔒 禁止使用任何代码块（如 ```python ... ```）
4. 🔒🔒🔒 禁止使用反引号包裹的代码（如 `print()`）
5. 🔒 不要问对话式问题，学生无法回复
6. 用自然语言描述问题和思路，不要写代码
7. 如果有语法错误，用文字解释错误类型和可能的原因
8. 如果逻辑错误，引导学生思考正确的逻辑方向
9. 分析要简短，语言简单，适合基础薄弱的学生理解
10.使用鼓励和支持的语气

请直接输出你的分析内容（不要包含代码）：
""".format(full_code=full_code, student_code=code, output=output, error=error, expected_output=expected_output)
        
        url = f'{AI_BASE_URL.rstrip("/")}/chat/completions'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {AI_API_KEY}',
        }
        payload = {
            'model': AI_MODEL,
            'messages': [
                {'role': 'system', 'content': '''
你是一位有耐心的Python编程老师，专门指导基础薄弱的学生。

重要说明：这是一次性的单向分析，你只需要输出分析内容，学生无法回复你的问题或继续对话。

特别注意：学生代码中可能包含 ①②③④⑤⑥⑦⑧⑨⑩ 等带圈数字符号，这些是填空占位符，表示学生尚未填写的位置，不代表学生实际编写的代码。

你的教学原则：
1. 绝对不给出直接答案或完整代码
2. 用文字分析帮助学生理解问题，不是提问
3. 语言要简单易懂
4. 鼓励学生自己尝试
5. 可以讲解基本概念和算法思路
6. 记住：学生只能看到你的分析内容，无法回复你，所以不要问"有什么问题可以问我"之类的话
'''},
                {'role': 'user', 'content': prompt.strip()},
            ],
            'max_tokens': 1000,
            'temperature': 0.3,
            'stream': False,
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        
        if response.status_code != 200:
            return jsonify({'error': f'AI 服务返回错误: {response.text[:200]}'}), 500
        
        result = response.json()
        evaluation = result['choices'][0]['message']['content']
        
        # 更新 AI 使用统计
        if problem_id:
            user_id = session['user_id']
            models.add_submission(user_id, problem_id, code, '', 0, run_count=0, ai_count=1)
            # 获取更新后的统计信息
            user_stats = models.get_user_submission_stats(user_id, problem_id)
            return jsonify({'evaluation': evaluation, 'user_stats': user_stats})
        
        return jsonify({'evaluation': evaluation})
    
    except requests.exceptions.Timeout:
        return jsonify({'error': 'AI 服务请求超时'}), 504
    except Exception as e:
        return jsonify({'error': f'AI 评审失败: {str(e)}'}), 500

@app.route('/api/user_stats')
@login_required
def api_user_stats():
    """获取用户统计"""
    user_id = session['user_id']
    problem_id = request.args.get('problem_id')
    
    if problem_id:
        stats = models.get_user_submission_stats(user_id, int(problem_id))
    else:
        stats = models.get_user_submission_stats(user_id)
    
    return jsonify(stats)

# ------------------------------
# 异步代码执行（支持 input）
# ------------------------------
@app.route('/api/start_execution', methods=['POST'])
@login_required
def api_start_execution():
    """启动异步代码执行"""
    code = request.json.get('code')
    if not code:
        return jsonify({'error': '请提供代码'}), 400
    
    last_run = session.get('last_run_time', 0)
    now = time.time()
    if now - last_run < RUN_COOLDOWN:
        return jsonify({'error': f'请等待 {int(RUN_COOLDOWN - (now - last_run))} 秒后再运行'})
    
    session['last_run_time'] = now
    
    execution_id = code_executor.start_execution(code)
    return jsonify({'execution_id': execution_id})

@app.route('/api/execution_status/<execution_id>')
@login_required
def api_execution_status(execution_id):
    """检查执行状态"""
    status = code_executor.get_execution_status(execution_id)
    if status is None:
        return jsonify({'error': '执行未找到'}), 404
    return jsonify(status)

@app.route('/api/provide_input/<execution_id>', methods=['POST'])
@login_required
def api_provide_input(execution_id):
    """提供输入"""
    input_value = request.json.get('input')
    if input_value is None:
        return jsonify({'error': '请提供输入'}), 400
    success = code_executor.provide_input(execution_id, input_value)
    if not success:
        return jsonify({'error': '无法提供输入'}), 400
    return jsonify({'success': True})

# ============================================================================
# 启动
# ============================================================================
if __name__ == '__main__':
    os.makedirs('logs', exist_ok=True)
    os.makedirs('uploads', exist_ok=True)
    
    # 初始化数据库
    models.init_db()
    models.init_sample_data()
    
    print('启动 Flask 应用: http://127.0.0.1:8085')
    app.run(debug=False, host='0.0.0.0', port=8080)