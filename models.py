"""
数据库模型定义 - Python 在线编程教学平台

包含：用户表、班级表、题目表、答题记录表
"""
import sqlite3
import hashlib
import os
import datetime

# 数据库路径 - 使用绝对路径确保数据一致性
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

def get_db_connection():
    """获取数据库连接并设置时区为本地时间"""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.execute('PRAGMA timezone = local')
    return conn

def get_local_time():
    """获取本地时间字符串（YYYY-MM-DD HH:MM:SS）"""
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def convert_utc_to_local(utc_dt_str):
    """将UTC时间字符串转换为本地时间字符串"""
    if not utc_dt_str:
        return utc_dt_str
    try:
        utc_dt = datetime.datetime.strptime(utc_dt_str, '%Y-%m-%d %H:%M:%S')
        local_dt = utc_dt + datetime.timedelta(hours=8)
        return local_dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return utc_dt_str

def init_db():
    """初始化数据库表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    conn.execute('PRAGMA timezone = local')

    # 用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('student', 'teacher')),
            name TEXT NOT NULL,
            class_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (class_id) REFERENCES classes(id)
        )
    ''')

    # 班级表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade TEXT NOT NULL CHECK(grade IN ('高一', '高二', '高三', '其他')),
            class_number TEXT NOT NULL,
            UNIQUE(grade, class_number)
        )
    ''')

    # 题目表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS problems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            full_code TEXT NOT NULL,
            student_code TEXT NOT NULL,
            expected_output TEXT NOT NULL,
            is_today INTEGER DEFAULT 0 CHECK(is_today IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 答题记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            problem_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            output TEXT,
            is_passed INTEGER DEFAULT 0 CHECK(is_passed IN (0, 1)),
            run_count INTEGER DEFAULT 1,
            ai_count INTEGER DEFAULT 0,
            passed_code TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (problem_id) REFERENCES problems(id)
        )
    ''')

    # 检查并添加 passed_code 字段（用于已有数据库的升级）
    try:
        cursor.execute('ALTER TABLE submissions ADD COLUMN passed_code TEXT')
    except sqlite3.OperationalError:
        pass  # 字段已存在

    # 系统配置表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 初始化注册开关配置（默认开放注册）
    cursor.execute('INSERT OR IGNORE INTO config (key, value) VALUES ("registration_enabled", "1")')

    # 积分记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            points INTEGER NOT NULL DEFAULT 0,
            total_points INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # 奖励领取记录表（记录每道题是否已领取奖励）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            problem_id INTEGER NOT NULL,
            points_earned INTEGER NOT NULL DEFAULT 0,
            chest_level TEXT,
            claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (problem_id) REFERENCES problems(id),
            UNIQUE(user_id, problem_id)
        )
    ''')

    # 用户答题统计视图（用于快速查询）
    cursor.execute('DROP VIEW IF EXISTS user_problem_stats')
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS user_problem_stats AS
        SELECT 
            user_id, 
            problem_id,
            COUNT(*) as total_submissions,
            SUM(run_count) as total_runs,
            SUM(ai_count) as total_ai_uses,
            MAX(is_passed) as ever_passed,
            MAX(submitted_at) as last_submission,
            (SELECT submitted_at FROM submissions s2 
             WHERE s2.user_id = submissions.user_id 
             AND s2.problem_id = submissions.problem_id 
             AND s2.is_passed = 1 
             ORDER BY s2.submitted_at DESC LIMIT 1) as passed_at,
            (SELECT passed_code FROM submissions s2 
             WHERE s2.user_id = submissions.user_id 
             AND s2.problem_id = submissions.problem_id 
             AND s2.is_passed = 1 
             ORDER BY s2.submitted_at DESC LIMIT 1) as passed_code
        FROM submissions
        GROUP BY user_id, problem_id
    ''')

    conn.commit()
    conn.close()

def hash_password(password):
    """密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()

def add_class(grade, class_number):
    """添加班级"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO classes (grade, class_number) VALUES (?, ?)', (grade, class_number))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # 班级已存在，返回现有ID
        cursor.execute('SELECT id FROM classes WHERE grade = ? AND class_number = ?', (grade, class_number))
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
        conn.close()

def add_student(username, password, name, class_id):
    """添加学生用户"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (username, password_hash, role, name, class_id)
            VALUES (?, ?, 'student', ?, ?)
        ''', (username, hash_password(password), name, class_id))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None  # 用户名已存在
    finally:
        conn.close()

def add_teacher(username, password, name):
    """添加教师用户"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (username, password_hash, role, name)
            VALUES (?, ?, 'teacher', ?)
        ''', (username, hash_password(password), name))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None  # 用户名已存在
    finally:
        conn.close()

def authenticate(username, password):
    """用户认证"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, role, name, class_id FROM users 
        WHERE username = ? AND password_hash = ?
    ''', (username, hash_password(password)))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {
            'id': result[0],
            'username': result[1],
            'role': result[2],
            'name': result[3],
            'class_id': result[4]
        }
    return None

def get_user_by_id(user_id):
    """根据ID获取用户信息"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, role, name, class_id FROM users WHERE id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {
            'id': result[0],
            'username': result[1],
            'role': result[2],
            'name': result[3],
            'class_id': result[4]
        }
    return None

def get_class_by_id(class_id):
    """根据ID获取班级信息"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT grade, class_number FROM classes WHERE id = ?', (class_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {'grade': result[0], 'class_number': result[1]}
    return None

def get_all_classes():
    """获取所有班级"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, grade, class_number FROM classes ORDER BY grade, class_number')
    results = cursor.fetchall()
    conn.close()
    return [{'id': r[0], 'grade': r[1], 'class_number': r[2]} for r in results]

def get_or_create_class(grade, class_number):
    """获取或创建班级"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 先查找是否存在
    cursor.execute('SELECT id FROM classes WHERE grade = ? AND class_number = ?', (grade, class_number))
    result = cursor.fetchone()
    if result:
        class_id = result[0]
    else:
        # 创建新班级
        cursor.execute('INSERT INTO classes (grade, class_number) VALUES (?, ?)', (grade, class_number))
        conn.commit()
        class_id = cursor.lastrowid
    conn.close()
    return class_id

def add_problem(title, description, category, full_code, student_code, expected_output):
    """添加题目"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO problems (title, description, category, full_code, student_code, expected_output)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (title, description, category, full_code, student_code, expected_output))
    conn.commit()
    problem_id = cursor.lastrowid
    conn.close()
    return problem_id

def update_problem(problem_id, title, description, category, full_code, student_code, expected_output):
    """更新题目"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE problems 
        SET title = ?, description = ?, category = ?, full_code = ?, student_code = ?, 
            expected_output = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (title, description, category, full_code, student_code, expected_output, problem_id))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def get_problem_by_id(problem_id):
    """根据ID获取题目"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, description, category, full_code, student_code, expected_output, is_today 
        FROM problems WHERE id = ?
    ''', (problem_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {
            'id': result[0],
            'title': result[1],
            'description': result[2],
            'category': result[3],
            'full_code': result[4],
            'student_code': result[5],
            'expected_output': result[6],
            'is_today': result[7]
        }
    return None

def get_all_problems():
    """获取所有题目"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, description, category, is_today, created_at 
        FROM problems ORDER BY category, title
    ''')
    results = cursor.fetchall()
    conn.close()
    return [{
        'id': r[0],
        'title': r[1],
        'description': r[2],
        'category': r[3],
        'is_today': r[4],
        'created_at': convert_utc_to_local(r[5])
    } for r in results]

def get_problems_by_category(category):
    """按类别获取题目"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, description, category, is_today 
        FROM problems WHERE category = ? ORDER BY title
    ''', (category,))
    results = cursor.fetchall()
    conn.close()
    return [{
        'id': r[0],
        'title': r[1],
        'description': r[2],
        'category': r[3],
        'is_today': r[4]
    } for r in results]

def get_today_problems():
    """获取今日题目"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, description, category, full_code, student_code, expected_output 
        FROM problems WHERE is_today = 1 ORDER BY category, title
    ''')
    results = cursor.fetchall()
    conn.close()
    return [{
        'id': r[0],
        'title': r[1],
        'description': r[2],
        'category': r[3],
        'full_code': r[4],
        'student_code': r[5],
        'expected_output': r[6]
    } for r in results]

def set_today_problems(problem_ids):
    """设置今日题目"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 先清除所有今日题目标记
    cursor.execute('UPDATE problems SET is_today = 0')
    # 设置新的今日题目
    for problem_id in problem_ids:
        cursor.execute('UPDATE problems SET is_today = 1 WHERE id = ?', (problem_id,))
    conn.commit()
    conn.close()

def get_all_categories():
    """获取所有题目类别"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT category FROM problems ORDER BY category')
    results = cursor.fetchall()
    conn.close()
    return [r[0] for r in results]

def add_submission(user_id, problem_id, code, output, is_passed, run_count=1, ai_count=0, passed_code=None):
    """添加答题记录"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 如果通过，保存通过的代码（优先使用传入的passed_code，否则使用完整代码）
    if passed_code is None:
        passed_code = code if is_passed else None
    cursor.execute('''
        INSERT INTO submissions (user_id, problem_id, code, output, is_passed, run_count, ai_count, passed_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, problem_id, code, output, is_passed, run_count, ai_count, passed_code))
    conn.commit()
    conn.close()

def get_user_submission_stats(user_id, problem_id=None):
    """获取用户答题统计"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if problem_id:
        cursor.execute('''
            SELECT total_submissions, total_runs, total_ai_uses, ever_passed, last_submission, passed_code
            FROM user_problem_stats WHERE user_id = ? AND problem_id = ?
        ''', (user_id, problem_id))
        result = cursor.fetchone()
        conn.close()
        if result:
            return {
                'total_submissions': result[0],
                'total_runs': result[1],
                'total_ai_uses': result[2],
                'ever_passed': bool(result[3]),
                'last_submission': result[4],
                'passed_code': result[5]
            }
        return {'total_submissions': 0, 'total_runs': 0, 'total_ai_uses': 0, 'ever_passed': False, 'last_submission': None, 'passed_code': None}
    else:
        cursor.execute('''
            SELECT problem_id, total_submissions, total_runs, total_ai_uses, ever_passed, passed_code
            FROM user_problem_stats WHERE user_id = ?
        ''', (user_id,))
        results = cursor.fetchall()
        conn.close()
        return {r[0]: {
            'total_submissions': r[1],
            'total_runs': r[2],
            'total_ai_uses': r[3],
            'ever_passed': bool(r[4]),
            'passed_code': r[5]
        } for r in results}

def get_problem_stats(problem_id, grade='', class_number=''):
    """获取题目统计（支持班级筛选）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 构建查询条件
    query = '''
        SELECT 
            COUNT(DISTINCT u.id) as total_students,
            SUM(CASE WHEN ups.ever_passed = 1 THEN 1 ELSE 0 END) as passed_students,
            SUM(ups.total_runs) as total_runs,
            SUM(ups.total_ai_uses) as total_ai_uses
        FROM user_problem_stats ups
        JOIN users u ON ups.user_id = u.id
        LEFT JOIN classes c ON u.class_id = c.id
        WHERE ups.problem_id = ?
    '''
    params = [problem_id]
    
    # 添加班级筛选条件
    if grade:
        query += ' AND c.grade = ?'
        params.append(grade)
    if class_number:
        query += ' AND c.class_number = ?'
        params.append(class_number)
    
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.close()
    if result:
        total_students = result[0] if result[0] else 0
        passed_students = result[1] if result[1] else 0
        return {
            'total_students': total_students,
            'passed_students': passed_students,
            'pass_rate': (passed_students / total_students * 100) if total_students > 0 else 0,
            'total_runs': result[2] if result[2] else 0,
            'total_ai_uses': result[3] if result[3] else 0
        }
    return {'total_students': 0, 'passed_students': 0, 'pass_rate': 0, 'total_runs': 0, 'total_ai_uses': 0}

def get_single_student_stats(problem_id, user_id):
    """获取单个学生某题的答题详情"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = '''
        SELECT u.id, u.name, c.grade, c.class_number, s.total_runs, s.total_ai_uses, s.ever_passed, s.passed_at, s.passed_code
        FROM user_problem_stats s
        JOIN users u ON s.user_id = u.id
        LEFT JOIN classes c ON u.class_id = c.id
        WHERE s.problem_id = ? AND s.user_id = ? AND u.role = 'student'
    '''
    
    cursor.execute(query, (problem_id, user_id))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'user_id': result[0],
            'name': result[1],
            'grade': result[2],
            'class_number': result[3],
            'class_display': f"{result[2]}{result[3]}班" if result[2] and result[3] else '未知',
            'total_runs': result[4],
            'total_ai_uses': result[5],
            'ever_passed': bool(result[6]),
            'passed_at': convert_utc_to_local(result[7]),
            'passed_code': result[8]
        }
    return None

def get_all_student_stats(problem_id, grade='', class_number=''):
    """获取某题所有学生的答题详情（支持班级筛选）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = '''
        SELECT u.id, u.name, c.grade, c.class_number, s.total_runs, s.total_ai_uses, s.ever_passed, s.passed_at, s.passed_code
        FROM user_problem_stats s
        JOIN users u ON s.user_id = u.id
        LEFT JOIN classes c ON u.class_id = c.id
        WHERE s.problem_id = ? AND u.role = 'student'
    '''
    params = [problem_id]
    
    if grade:
        query += ' AND c.grade = ?'
        params.append(grade)
    if class_number:
        query += ' AND c.class_number = ?'
        params.append(class_number)
    
    query += ' ORDER BY c.grade, c.class_number, u.name'
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return [{
        'user_id': r[0],
        'name': r[1],
        'grade': r[2],
        'class_number': r[3],
        'class_display': f"{r[2]}{r[3]}班" if r[2] and r[3] else '未知',
        'total_runs': r[4],
        'total_ai_uses': r[5],
        'ever_passed': bool(r[6]),
        'passed_at': convert_utc_to_local(r[7]),
        'passed_code': r[8]
    } for r in results]

def delete_problem(problem_id):
    """删除题目"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM problems WHERE id = ?', (problem_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def get_all_grades():
    """获取所有年级"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT grade FROM classes ORDER BY grade')
    results = cursor.fetchall()
    conn.close()
    return [r[0] for r in results if r[0]]

def get_all_class_numbers():
    """获取所有班级编号"""
    return [str(i) for i in range(1, 21)]

def get_total_students():
    """获取学生总数"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = ?', ('student',))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def get_all_student_overall_stats(grade='', class_number=''):
    """获取所有学生的总体统计（支持班级筛选）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = '''
        SELECT u.id, u.name, 
               COUNT(DISTINCT ups.problem_id) as attempted_problems,
               SUM(CASE WHEN ups.ever_passed = 1 THEN 1 ELSE 0 END) as passed_problems,
               SUM(ups.total_runs) as total_runs,
               SUM(ups.total_ai_uses) as total_ai_uses
        FROM users u
        LEFT JOIN user_problem_stats ups ON u.id = ups.user_id
        LEFT JOIN classes c ON u.class_id = c.id
        WHERE u.role = 'student'
    '''
    params = []
    
    if grade:
        query += ' AND c.grade = ?'
        params.append(grade)
    if class_number:
        query += ' AND c.class_number = ?'
        params.append(class_number)
    
    query += ' GROUP BY u.id, u.name ORDER BY u.name'
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return [{
        'user_id': r[0],
        'name': r[1],
        'attempted_problems': r[2] if r[2] else 0,
        'passed_problems': r[3] if r[3] else 0,
        'total_runs': r[4] if r[4] else 0,
        'total_ai_uses': r[5] if r[5] else 0
    } for r in results]

def get_registration_enabled():
    """获取注册开关状态"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT value FROM config WHERE key = "registration_enabled"')
        result = cursor.fetchone()
        return result[0] == '1' if result else True
    except sqlite3.OperationalError:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('INSERT OR IGNORE INTO config (key, value) VALUES ("registration_enabled", "1")')
        conn.commit()
        return True
    finally:
        conn.close()

def set_registration_enabled(enabled):
    """设置注册开关状态"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE config SET value = ? WHERE key = "registration_enabled"', ('1' if enabled else '0',))
        conn.commit()
    except sqlite3.OperationalError:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('INSERT OR IGNORE INTO config (key, value) VALUES ("registration_enabled", "1")')
        cursor.execute('UPDATE config SET value = ? WHERE key = "registration_enabled"', ('1' if enabled else '0',))
        conn.commit()
    finally:
        conn.close()

def delete_student_data(grade='', class_number=''):
    """删除学生答题数据（保留账号）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = 'SELECT id FROM users WHERE role = "student"'
    params = []
    
    if grade:
        query += ' AND class_id IN (SELECT id FROM classes WHERE grade = ?)'
        params.append(grade)
    if class_number:
        if grade:
            query += ' AND class_id IN (SELECT id FROM classes WHERE grade = ? AND class_number = ?)'
            params.append(grade)
            params.append(class_number)
        else:
            query += ' AND class_id IN (SELECT id FROM classes WHERE class_number = ?)'
            params.append(class_number)
    
    cursor.execute(query, params)
    user_ids = [str(r[0]) for r in cursor.fetchall()]
    
    if user_ids:
        placeholders = ','.join('?' * len(user_ids))
        cursor.execute(f'DELETE FROM submissions WHERE user_id IN ({placeholders})', user_ids)
        cursor.execute(f'DELETE FROM rewards WHERE user_id IN ({placeholders})', user_ids)
        cursor.execute(f'DELETE FROM points WHERE user_id IN ({placeholders})', user_ids)
    
    conn.commit()
    conn.close()
    return len(user_ids)

def delete_student_accounts(grade='', class_number=''):
    """删除学生账号及所有数据"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = 'SELECT id FROM users WHERE role = "student"'
    params = []
    
    if grade:
        query += ' AND class_id IN (SELECT id FROM classes WHERE grade = ?)'
        params.append(grade)
    if class_number:
        if grade:
            query += ' AND class_id IN (SELECT id FROM classes WHERE grade = ? AND class_number = ?)'
            params.append(grade)
            params.append(class_number)
        else:
            query += ' AND class_id IN (SELECT id FROM classes WHERE class_number = ?)'
            params.append(class_number)
    
    cursor.execute(query, params)
    user_ids = [str(r[0]) for r in cursor.fetchall()]
    
    if user_ids:
        placeholders = ','.join('?' * len(user_ids))
        cursor.execute(f'DELETE FROM submissions WHERE user_id IN ({placeholders})', user_ids)
        cursor.execute(f'DELETE FROM rewards WHERE user_id IN ({placeholders})', user_ids)
        cursor.execute(f'DELETE FROM points WHERE user_id IN ({placeholders})', user_ids)
        cursor.execute(f'DELETE FROM users WHERE id IN ({placeholders})', user_ids)
    
    conn.commit()
    conn.close()
    return len(user_ids)

def search_students_by_name(name):
    """按姓名搜索学生"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, class_id FROM users WHERE role = "student" AND name LIKE ?', 
                  ('%' + name + '%',))
    results = cursor.fetchall()
    conn.close()
    students = []
    for r in results:
        class_info = get_class_by_id(r[2]) if r[2] else None
        class_display = f"{class_info['grade']}{class_info['class_number']}班" if class_info else '未知'
        students.append({
            'id': r[0],
            'name': r[1],
            'class_display': class_display
        })
    return students

def delete_student_by_id(user_id):
    """按ID删除单个学生的所有数据（含账号）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM submissions WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM rewards WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM points WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM users WHERE id = ? AND role = "student"', (user_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def delete_student_data_by_id(user_id):
    """按ID删除单个学生的答题数据（保留账号）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM submissions WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM rewards WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM points WHERE user_id = ?', (user_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def get_students_by_class(grade, class_number):
    """获取指定班级的学生列表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.id, u.name, c.grade, c.class_number 
        FROM users u 
        JOIN classes c ON u.class_id = c.id 
        WHERE u.role = "student" AND c.grade = ? AND c.class_number = ?
        ORDER BY u.name
    ''', (grade, class_number))
    results = cursor.fetchall()
    conn.close()
    return [{
        'id': r[0],
        'name': r[1],
        'class_display': f"{r[2]}{r[3]}班"
    } for r in results]

# 初始化示例数据
def init_sample_data():
    """初始化示例数据（创建班级和教师账号）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 创建班级
    grades = ['高一', '高二', '高三', '其他']
    class_numbers = ['1班', '2班', '3班', '4班', '5班']
    
    for grade in grades:
        for class_num in class_numbers:
            try:
                cursor.execute('INSERT INTO classes (grade, class_number) VALUES (?, ?)', (grade, class_num))
            except sqlite3.IntegrityError:
                pass

    # 创建10个教师账号
    teacher_names = ['张老师', '李老师', '王老师', '赵老师', '刘老师', 
                     '陈老师', '杨老师', '黄老师', '周老师', '吴老师']
    
    for i, name in enumerate(teacher_names, 1):
        username = f'teacher{i}'
        password = f'teacher{i}@2024'
        try:
            cursor.execute('''
                INSERT INTO users (username, password_hash, role, name)
                VALUES (?, ?, 'teacher', ?)
            ''', (username, hash_password(password), name))
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()

    print("示例数据初始化完成！")
    print("教师账号：teacher1~teacher10")
    print("教师密码：teacher1@2024~teacher10@2024")

# ------------------------------
# 积分系统函数
# ------------------------------

def get_user_points(user_id):
    """获取用户积分"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT points, total_points FROM points WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {'points': result[0], 'total_points': result[1]}
    return {'points': 0, 'total_points': 0}

def add_user_points(user_id, points):
    """增加用户积分"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT points, total_points FROM points WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if result:
            new_points = result[0] + points
            new_total = result[1] + points
            cursor.execute('UPDATE points SET points = ?, total_points = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                          (new_points, new_total, user_id))
        else:
            cursor.execute('INSERT INTO points (user_id, points, total_points) VALUES (?, ?, ?)',
                          (user_id, points, points))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        return False
    finally:
        conn.close()

def has_claimed_reward(user_id, problem_id):
    """检查用户是否已领取某题的奖励"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM rewards WHERE user_id = ? AND problem_id = ?', (user_id, problem_id))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def claim_reward(user_id, problem_id, points_earned, chest_level):
    """领取奖励"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO rewards (user_id, problem_id, points_earned, chest_level)
            VALUES (?, ?, ?, ?)
        ''', (user_id, problem_id, points_earned, chest_level))
        
        cursor.execute('SELECT points, total_points FROM points WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if result:
            new_points = result[0] + points_earned
            new_total = result[1] + points_earned
            cursor.execute('UPDATE points SET points = ?, total_points = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                          (new_points, new_total, user_id))
        else:
            cursor.execute('INSERT INTO points (user_id, points, total_points) VALUES (?, ?, ?)',
                          (user_id, points_earned, points_earned))
        
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        conn.rollback()
        return False
    finally:
        conn.close()

def get_user_reward(user_id, problem_id):
    """获取用户某题的奖励记录"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT points_earned, chest_level, claimed_at FROM rewards WHERE user_id = ? AND problem_id = ?',
                  (user_id, problem_id))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {
            'points_earned': result[0],
            'chest_level': result[1],
            'claimed_at': convert_utc_to_local(result[2])
        }
    return None

def get_leaderboard(limit=10):
    """获取积分榜前N名"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.id, u.name, u.username, c.grade, c.class_number, 
               COALESCE(p.points, 0) as points, COALESCE(p.total_points, 0) as total_points
        FROM users u
        LEFT JOIN points p ON u.id = p.user_id
        LEFT JOIN classes c ON u.class_id = c.id
        WHERE u.role = 'student'
        ORDER BY COALESCE(p.points, 0) DESC
        LIMIT ?
    ''', (limit,))
    results = cursor.fetchall()
    conn.close()
    return [{
        'user_id': r[0],
        'name': r[1],
        'username': r[2],
        'grade': r[3],
        'class_number': r[4],
        'class_display': f"{r[3]}{r[4]}班" if r[3] and r[4] else '未知',
        'points': r[5],
        'total_points': r[6]
    } for r in results]

if __name__ == '__main__':
    init_db()
    init_sample_data()
    print("数据库初始化完成！")