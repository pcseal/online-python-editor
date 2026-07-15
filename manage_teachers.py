import sqlite3
import hashlib
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

def hash_password(password):
    """密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()

def get_connection():
    """获取数据库连接"""
    return sqlite3.connect(DB_PATH)

def list_teachers():
    """列出所有教师账号"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, name, created_at FROM users WHERE role = "teacher" ORDER BY id')
    teachers = cursor.fetchall()
    conn.close()
    
    if not teachers:
        print("暂无教师账号")
        return
    
    print(f"\n{'ID':<5} {'用户名':<15} {'姓名':<10} {'创建时间'}")
    print("-" * 60)
    for t in teachers:
        print(f"{t[0]:<5} {t[1]:<15} {t[2]:<10} {t[3]}")
    print()

def add_teacher():
    """添加教师账号"""
    username = input("请输入教师用户名: ").strip()
    if not username:
        print("用户名不能为空")
        return
    
    name = input("请输入教师姓名: ").strip()
    if not name:
        print("姓名不能为空")
        return
    
    password = input("请输入密码: ").strip()
    if len(password) < 6:
        print("密码至少6位")
        return
    
    confirm_password = input("请确认密码: ").strip()
    if password != confirm_password:
        print("两次密码不一致")
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (username, password_hash, role, name)
            VALUES (?, ?, 'teacher', ?)
        ''', (username, hash_password(password), name))
        conn.commit()
        print(f"\n教师账号 {username} 创建成功！")
    except sqlite3.IntegrityError:
        print(f"\n错误：用户名 {username} 已存在")
    finally:
        conn.close()

def modify_teacher():
    """修改教师账号"""
    list_teachers()
    
    username = input("\n请输入要修改的教师用户名: ").strip()
    if not username:
        print("用户名不能为空")
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM users WHERE username = ? AND role = "teacher"', (username,))
    teacher = cursor.fetchone()
    
    if not teacher:
        print(f"未找到教师账号: {username}")
        conn.close()
        return
    
    print(f"\n当前信息：")
    print(f"  ID: {teacher[0]}")
    print(f"  用户名: {username}")
    print(f"  姓名: {teacher[1]}")
    
    print("\n修改选项：")
    print("  1. 修改姓名")
    print("  2. 修改密码")
    print("  3. 修改姓名和密码")
    
    choice = input("请选择(1/2/3): ").strip()
    
    new_name = teacher[1]
    new_password = None
    
    if choice in ['1', '3']:
        new_name = input("请输入新姓名: ").strip()
        if not new_name:
            print("姓名不能为空")
            conn.close()
            return
    
    if choice in ['2', '3']:
        new_password = input("请输入新密码: ").strip()
        if len(new_password) < 6:
            print("密码至少6位")
            conn.close()
            return
        
        confirm_password = input("请确认新密码: ").strip()
        if new_password != confirm_password:
            print("两次密码不一致")
            conn.close()
            return
    
    try:
        if new_password:
            cursor.execute('''
                UPDATE users SET name = ?, password_hash = ? WHERE username = ?
            ''', (new_name, hash_password(new_password), username))
        else:
            cursor.execute('''
                UPDATE users SET name = ? WHERE username = ?
            ''', (new_name, username))
        conn.commit()
        print(f"\n教师账号 {username} 修改成功！")
    except Exception as e:
        print(f"\n修改失败: {e}")
    finally:
        conn.close()

def delete_teacher():
    """删除教师账号"""
    list_teachers()
    
    username = input("\n请输入要删除的教师用户名: ").strip()
    if not username:
        print("用户名不能为空")
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM users WHERE username = ? AND role = "teacher"', (username,))
    teacher = cursor.fetchone()
    
    if not teacher:
        print(f"未找到教师账号: {username}")
        conn.close()
        return
    
    print(f"\n确认删除教师账号：")
    print(f"  ID: {teacher[0]}")
    print(f"  用户名: {username}")
    print(f"  姓名: {teacher[1]}")
    
    confirm = input("\n此操作不可撤销，确认删除吗？(y/N): ").strip().lower()
    if confirm != 'y':
        print("已取消删除")
        conn.close()
        return
    
    try:
        cursor.execute('DELETE FROM users WHERE username = ? AND role = "teacher"', (username,))
        conn.commit()
        print(f"\n教师账号 {username} 删除成功！")
    except Exception as e:
        print(f"\n删除失败: {e}")
    finally:
        conn.close()

def show_help():
    """显示帮助信息"""
    print("""
教师账号管理脚本

用法: python manage_teachers.py <命令>

命令:
  list          列出所有教师账号
  add           添加新教师账号
  modify        修改教师账号（姓名/密码）
  delete        删除教师账号
  help          显示帮助信息

示例:
  python manage_teachers.py list
  python manage_teachers.py add
  python manage_teachers.py modify
  python manage_teachers.py delete
""")

def main():
    if len(sys.argv) < 2:
        show_help()
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == 'list':
        list_teachers()
    elif command == 'add':
        add_teacher()
    elif command == 'modify':
        modify_teacher()
    elif command == 'delete':
        delete_teacher()
    elif command == 'help':
        show_help()
    else:
        print(f"未知命令: {command}")
        show_help()
        sys.exit(1)

if __name__ == '__main__':
    main()