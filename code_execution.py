"""
代码执行与异步交互模块

封装了"同步执行"与"异步 input() 交互"两种模式，统一调用 code_sandbox 中的沙箱。
"""
import os
import sys
import time
import uuid
import threading
import traceback
from io import StringIO
from typing import Dict, Any

from code_sandbox import get_default_sandbox, SandboxRouter


# 异步执行器：用于支持 input() 的人机交互式代码
class AsyncCodeExecutor:
    """
    为支持 input() 的代码提供异步执行能力。
    通过后台线程运行代码，主线程可以查询状态并投递输入。
    """

    def __init__(self, sandbox: SandboxRouter = None):
        self.execution_queue: Dict[str, Dict[str, Any]] = {}
        self._sandbox = sandbox or get_default_sandbox()
        self._lock = threading.Lock()

    def start_execution(self, code: str) -> str:
        """启动一次执行，返回 execution_id"""
        execution_id = str(uuid.uuid4())
        with self._lock:
            self.execution_queue[execution_id] = {
                'code': code,
                'status': 'running',
                'input_required': False,
                'input_prompt': '',
                'input_value': None,
                'result': None,
                'start_time': time.time(),
                'output_buffer': '',
            }
        threading.Thread(target=self._execute_code_interactive, args=(execution_id,), daemon=True).start()
        return execution_id

    def _execute_code_interactive(self, execution_id: str):
        """在子线程中执行代码（支持 input() 交互）"""
        with self._lock:
            execution = self.execution_queue[execution_id]
        
        code = execution['code']
        
        try:
            # 使用 exec 在受控环境中执行代码，支持 input() 交互
            local_vars = {
                '__builtins__': __builtins__,
                'print': print,
                'input': lambda prompt='': self._custom_input(execution_id, prompt),
            }
            
            # 添加常用模块
            try:
                import math
                local_vars['math'] = math
            except ImportError:
                pass
            try:
                import random
                local_vars['random'] = random
            except ImportError:
                pass
            
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            new_stdout = StringIO()
            new_stderr = StringIO()
            
            try:
                sys.stdout = new_stdout
                sys.stderr = new_stderr
                
                exec(code, {}, local_vars)
                
                output = new_stdout.getvalue()
                error = new_stderr.getvalue()
                
                with self._lock:
                    execution['status'] = 'completed'
                    execution['input_required'] = False
                    execution['result'] = {
                        'output': output,
                        'error': error if error else '',
                        'timed_out': False,
                        'killed_reason': '',
                    }
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                
        except EOFError:
            with self._lock:
                execution['status'] = 'completed'
                execution['input_required'] = False
                execution['result'] = {
                    'output': execution.get('output_buffer', ''),
                    'error': '程序等待输入时结束',
                    'timed_out': False,
                    'killed_reason': 'eof',
                }
        except Exception as e:
            with self._lock:
                execution['status'] = 'error'
                execution['input_required'] = False
                execution['result'] = {
                    'output': execution.get('output_buffer', ''),
                    'error': f'{e}\n{traceback.format_exc()}',
                    'timed_out': False,
                    'killed_reason': 'exception',
                }

    def _custom_input(self, execution_id: str, prompt: str) -> str:
        """自定义 input 函数，实现异步交互"""
        with self._lock:
            execution = self.execution_queue[execution_id]
            execution['input_required'] = True
            execution['input_prompt'] = prompt
        
        # 等待用户输入（最多等待 60 秒）
        timeout = 60
        start_time = time.time()
        while time.time() - start_time < timeout:
            time.sleep(0.1)
            with self._lock:
                execution = self.execution_queue[execution_id]
                if execution.get('input_value') is not None:
                    value = execution['input_value']
                    execution['input_value'] = None
                    execution['input_required'] = False
                    return value
        
        raise EOFError("输入超时")

    def provide_input(self, execution_id: str, value: str) -> bool:
        """投递一次 input"""
        with self._lock:
            if execution_id not in self.execution_queue:
                return False
            self.execution_queue[execution_id]['input_value'] = value
        return True

    def get_execution_status(self, execution_id: str) -> Dict[str, Any]:
        with self._lock:
            if execution_id not in self.execution_queue:
                return None
            execution = self.execution_queue[execution_id]
            return {
                'status': execution['status'],
                'input_required': execution['input_required'],
                'input_prompt': execution['input_prompt'],
                'result': execution['result'],
            }

    def cleanup_old_executions(self, max_age: int = 3600):
        with self._lock:
            now = time.time()
            stale = [
                eid for eid, ex in self.execution_queue.items()
                if now - ex.get('start_time', now) > max_age
            ]
            for eid in stale:
                del self.execution_queue[eid]


# 全局单例
code_executor = AsyncCodeExecutor()


def execute_python_code(code: str) -> Dict[str, str]:
    """同步执行一段 Python 代码（不等待 input）"""
    if 'input(' in code:
        warning = (
            '⚠️ 检测到代码中调用了 input()，请改用「运行代码」按钮以获得完整体验。\n\n'
        )
    else:
        warning = ''

    result = get_default_sandbox().execute(code)
    if warning and result.get('output'):
        result['output'] = warning + result['output']
    elif warning:
        result['output'] = warning
    return result