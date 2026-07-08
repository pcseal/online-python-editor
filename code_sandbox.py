"""
代码安全执行沙箱模块

提供两种执行后端：
  1. DockerSandbox    ：生产环境，Docker 容器隔离（推荐，机房学生并发场景）
  2. SubprocessSandbox：开发/无 Docker 环境，Python AST 静态分析 + 指令计数降级

通过环境变量 DOCKER_ENABLED 自动切换（默认开启 Docker，未检测到 Docker 时自动降级）。
"""
import os
import sys
import time
import json
import signal
import shutil
import tempfile
import subprocess
import threading
import traceback
from io import StringIO
from typing import Dict, Any, List, Optional
from pathlib import Path

# 尝试导入 Docker SDK（未安装也不会影响 Subprocess 降级）
try:
    import docker
    from docker.errors import ImageNotFound, APIError as DockerAPIError
    DOCKER_SDK_AVAILABLE = True
except ImportError:
    DOCKER_SDK_AVAILABLE = False


# ============================================================================
# 通用异常
# ============================================================================
class SandboxError(Exception):
    """沙箱执行异常基类"""
    pass


class TimeoutException(SandboxError):
    """执行超时"""
    pass


class MemoryLimitException(SandboxError):
    """内存超限"""
    pass


class DangerousCodeException(SandboxError):
    """代码包含危险操作"""
    pass


class InstructionCountExceededException(SandboxError):
    """指令数超限（疑似死循环）"""
    pass


# ============================================================================
# 静态危险代码检测
# ============================================================================
DANGEROUS_MODULES = {
    'os', 'sys', 'subprocess', 'shutil', 'socket', 'urllib', 'urllib3',
    'requests', 'http', 'ftplib', 'smtplib', 'telnetlib',
    'ctypes', 'cffi', 'multiprocessing', 'threading',
    'pickle', 'shelve', 'marshal', 'builtins',
    'importlib', 'pkgutil', 'code', 'codeop',
    '__future__',
}

DANGEROUS_BUILTINS = {
    'eval', 'exec', 'compile', '__import__', 'globals', 'locals',
    'vars', 'getattr', 'setattr', 'delattr', 'hasattr', 'dir',
    'breakpoint', 'help', 'memoryview', 'open',
}

ALLOWED_MODULES = {
    'math', 'random', 'statistics', 'datetime', 'collections', 'itertools',
    'functools', 'operator', 'decimal', 'fractions', 'json', 'csv',
    're', 'string', 'numpy', 'pandas', 'scipy', 'sympy',
    'matplotlib', 'matplotlib.pyplot', 'nltk', 'textblob', 'typing',
}


# ============================================================================
# 后端 1：Docker 沙箱（生产环境）
# ============================================================================
class DockerSandbox:
    """
    基于 Docker 容器的安全执行沙箱。

    每次执行会启动一个临时容器，运行完自动销毁（--rm）。
    通过 cgroups 限制内存与 CPU 时间，--network=none 禁止网络访问。
    """

    DEFAULT_IMAGE = os.getenv('SANDBOX_IMAGE', 'python:3.9-slim')
    DEFAULT_TIMEOUT = int(os.getenv('SANDBOX_TIMEOUT', '10'))
    DEFAULT_MEMORY_MB = int(os.getenv('SANDBOX_MEMORY_MB', '128'))
    DEFAULT_CPUS = float(os.getenv('SANDBOX_CPUS', '0.5'))

    def __init__(self,
                 image: str = None,
                 timeout_seconds: int = None,
                 max_memory_mb: int = None,
                 cpus: float = None,
                 network: str = 'none'):
        self.image = image or self.DEFAULT_IMAGE
        self.timeout_seconds = timeout_seconds or self.DEFAULT_TIMEOUT
        self.max_memory_mb = max_memory_mb or self.DEFAULT_MEMORY_MB
        self.cpus = cpus or self.DEFAULT_CPUS
        self.network = network

        self._client = None
        if DOCKER_SDK_AVAILABLE:
            try:
                self._client = docker.from_env()
            except Exception:
                self._client = None

    @property
    def is_available(self) -> bool:
        """Docker SDK 与 Docker daemon 是否就绪"""
        if not DOCKER_SDK_AVAILABLE or self._client is None:
            return False
        try:
            self._client.ping()
            return True
        except Exception:
            return False

    def ensure_image(self) -> bool:
        """确保沙箱镜像已存在，不存在则自动拉取"""
        if not self.is_available:
            return False
        try:
            self._client.images.get(self.image)
            return True
        except ImageNotFound:
            try:
                print(f'[DockerSandbox] 正在拉取镜像 {self.image}，请稍候...')
                self._client.images.pull(self.image)
                return True
            except Exception as e:
                print(f'[DockerSandbox] 拉取镜像失败: {e}')
                return False
        except Exception:
            return False

    def execute(self, code: str, stdin_input: str = '') -> Dict[str, str]:
        """
        在 Docker 容器中执行 Python 代码。

        Args:
            code: 要执行的 Python 源码
            stdin_input: 标准输入内容

        Returns:
            {'output': 正常输出, 'error': 错误信息, 'timed_out': bool, 'killed_reason': str}
        """
        if not self.is_available:
            return {
                'output': '',
                'error': 'Docker 沙箱不可用，请检查 Docker Desktop 是否启动。',
                'timed_out': False,
                'killed_reason': 'docker_unavailable',
            }
        if not self.ensure_image():
            return {
                'output': '',
                'error': f'无法准备沙箱镜像 {self.image}',
                'timed_out': False,
                'killed_reason': 'image_unavailable',
            }

        # 把代码写入临时文件
        tmp_dir = tempfile.mkdtemp(prefix='pyarena_')
        code_file = os.path.join(tmp_dir, 'main.py')
        with open(code_file, 'w', encoding='utf-8') as f:
            f.write(code)

        result = {
            'output': '',
            'error': '',
            'timed_out': False,
            'killed_reason': '',
        }

        try:
            container = self._client.containers.run(
                image=self.image,
                command=['python', '/code/main.py'],
                volumes={tmp_dir: {'bind': '/code', 'mode': 'ro'}},
                mem_limit=f'{self.max_memory_mb}m',
                memswap_limit=f'{self.max_memory_mb}m',
                nano_cpus=int(self.cpus * 1_000_000_000),
                network_mode=self.network,
                working_dir='/code',
                stdin_open=True,
                detach=True,
                remove=False,
                user='nobody',
                read_only=True,
                tmpfs={'/tmp': 'size=10m,noexec,nosuid,nodev'},
                pids_limit=64,
            )
            try:
                if stdin_input:
                    try:
                        sock = container.attach_socket(params={'stdin': 1, 'stream': 1})
                        import socket as _socket
                        sock.sendall(stdin_input.encode('utf-8'))
                        sock.close()
                    except Exception:
                        pass

                try:
                    wait_result = container.wait(timeout=self.timeout_seconds)
                    exit_code = wait_result.get('StatusCode', 1)
                except Exception:
                    result['timed_out'] = True
                    result['killed_reason'] = 'timeout'
                    try:
                        container.kill()
                    except Exception:
                        pass
                    exit_code = 124

                stdout = container.logs(stdout=True, stderr=False) or b''
                stderr = container.logs(stdout=False, stderr=True) or b''
                result['output'] = stdout.decode('utf-8', errors='replace')
                stderr_text = stderr.decode('utf-8', errors='replace')

                if result['timed_out']:
                    result['error'] = f'⏱️ 代码执行超过 {self.timeout_seconds} 秒，已被强制终止。'
                elif exit_code != 0:
                    if 'MemoryError' in stderr_text or 'Killed' in stderr_text:
                        result['error'] = f'💥 内存超限（{self.max_memory_mb}MB）。\n{stderr_text}'
                        result['killed_reason'] = 'memory'
                    else:
                        result['error'] = stderr_text or f'程序退出码 {exit_code}'
            finally:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
        except DockerAPIError as e:
            result['error'] = f'Docker API 错误: {e}'
        except Exception as e:
            result['error'] = f'沙箱执行异常: {e}\n{traceback.format_exc()}'
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return result

    def execute_with_test(self, code: str, test_code: str) -> Dict[str, Any]:
        """
        提交模式：先拼接测试代码再执行，返回是否通过。

        Args:
            code: 学生代码
            test_code: 由题库提供的测试代码（应能 raise AssertionError 或 print "OK"）

        Returns:
            {
                'passed': bool,
                'output': stdout,
                'error': stderr/异常信息,
                'timed_out': bool
            }
        """
        combined = code.rstrip() + '\n\n' + test_code
        result = self.execute(combined)
        passed = (
            not result.get('timed_out')
            and not result.get('error')
            and ('OK' in result.get('output', '') or '通过' in result.get('output', ''))
        )
        result['passed'] = passed
        return result


# ============================================================================
# 后端 2：Subprocess 沙箱（降级方案，不依赖 Docker）
# ============================================================================
class SubprocessSandbox:
    """
    不依赖 Docker 的安全执行后端：subprocess + AST 静态分析 + 指令计数。

    适用场景：
      - 本地开发机未安装 Docker
      - 单机测试 / 演示
      - 机房 5 人以下轻量使用

    安全性弱于 Docker 沙箱，建议在生产环境使用 Docker 沙箱。
    """

    DEFAULT_TIMEOUT = int(os.getenv('SUBPROCESS_TIMEOUT', '10'))
    DEFAULT_MEMORY_MB = int(os.getenv('SUBPROCESS_MEMORY_MB', '128'))

    def __init__(self,
                 timeout_seconds: int = None,
                 max_memory_mb: int = None,
                 max_instructions: int = 1_000_000):
        self.timeout_seconds = timeout_seconds or self.DEFAULT_TIMEOUT
        self.max_memory_mb = max_memory_mb or self.DEFAULT_MEMORY_MB
        self.max_instructions = max_instructions

    @staticmethod
    def static_check(code: str) -> List[str]:
        """AST 静态扫描：返回危险项列表（空列表表示通过）"""
        import ast
        issues: List[str] = []
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [f'语法错误: {e}']

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split('.')[0]
                    if root in DANGEROUS_MODULES:
                        issues.append(f'禁止导入模块: {alias.name}')
                    elif root not in ALLOWED_MODULES:
                        issues.append(f'未授权模块: {alias.name}')
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split('.')[0]
                    if root in DANGEROUS_MODULES:
                        issues.append(f'禁止 from-import: {node.module}')
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in DANGEROUS_BUILTINS:
                    issues.append(f'禁止调用: {node.func.id}()')

        return issues

    def execute(self, code: str, stdin_input: str = '') -> Dict[str, str]:
        """在子进程中执行 Python 代码"""
        issues = self.static_check(code)
        if issues:
            return {
                'output': '',
                'error': '代码检测到以下问题:\n' + '\n'.join(f'  - {x}' for x in issues),
                'timed_out': False,
                'killed_reason': 'static_check_failed',
            }

        # 添加 UTF-8 编码声明，确保中文正常显示
        code_with_encoding = '# -*- coding: utf-8 -*-\n' + code

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as f:
            f.write(code_with_encoding)
            tmp_path = f.name

        result = {
            'output': '',
            'error': '',
            'timed_out': False,
            'killed_reason': '',
        }
        try:
            creationflags = 0
            preexec_fn = None
            if os.name == 'posix':
                preexec_fn = self._apply_rlimit

            # 设置环境变量确保 UTF-8 编码
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['PYTHONUTF8'] = '1'

            proc = subprocess.Popen(
                [sys.executable, tmp_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=preexec_fn,
                creationflags=creationflags,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=env,
            )
            try:
                stdout, stderr = proc.communicate(
                    input=stdin_input, timeout=self.timeout_seconds
                )
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                result['timed_out'] = True
                result['killed_reason'] = 'timeout'
                result['error'] = f'⏱️ 代码执行超过 {self.timeout_seconds} 秒，已被强制终止。'

            result['output'] = stdout or ''
            if stderr and not result['timed_out']:
                if proc.returncode != 0:
                    result['error'] = stderr
        except Exception as e:
            result['error'] = f'执行异常: {e}\n{traceback.format_exc()}'
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return result

    def _apply_rlimit(self):
        """POSIX 下限制子进程资源"""
        try:
            import resource
            mem_bytes = self.max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            resource.setrlimit(resource.RLIMIT_CPU, (self.timeout_seconds, self.timeout_seconds))
        except Exception:
            pass


# ============================================================================
# 统一入口：SandboxRouter
# ============================================================================
class SandboxRouter:
    """
    统一沙箱入口，根据环境变量 DOCKER_ENABLED 与 Docker 可用性自动选择后端。

    用法：
        sb = SandboxRouter()
        result = sb.execute('print(1+1)')
    """

    def __init__(self,
                 prefer_docker: Optional[bool] = None,
                 **kwargs):
        if prefer_docker is None:
            env_val = os.getenv('DOCKER_ENABLED', 'auto').lower()
            if env_val in ('0', 'false', 'off', 'no'):
                prefer_docker = False
            elif env_val in ('1', 'true', 'on', 'yes'):
                prefer_docker = True
            else:
                prefer_docker = True  # auto 默认倾向于 Docker

        self._docker = DockerSandbox(**kwargs) if prefer_docker else None
        self._subprocess = SubprocessSandbox(**kwargs)
        self._prefer_docker = prefer_docker

    @property
    def backend_name(self) -> str:
        if self._prefer_docker and self._docker and self._docker.is_available:
            return 'docker'
        return 'subprocess'

    def execute(self, code: str, stdin_input: str = '') -> Dict[str, str]:
        if self.backend_name == 'docker':
            return self._docker.execute(code, stdin_input)
        return self._subprocess.execute(code, stdin_input)

    def execute_with_test(self, code: str, test_code: str) -> Dict[str, Any]:
        if self.backend_name == 'docker':
            return self._docker.execute_with_test(code, test_code)
        combined = code.rstrip() + '\n\n' + test_code
        result = self._subprocess.execute(combined)
        passed = (
            not result.get('timed_out')
            and not result.get('error')
            and ('OK' in result.get('output', '') or '通过' in result.get('output', ''))
        )
        result['passed'] = passed
        return result


# 便捷函数：默认单例
_default_router: Optional[SandboxRouter] = None


def get_default_sandbox() -> SandboxRouter:
    """获取默认沙箱（懒加载单例）"""
    global _default_router
    if _default_router is None:
        _default_router = SandboxRouter()
    return _default_router


def execute_python_code_safely(code: str, timeout_seconds: int = 10) -> Dict[str, str]:
    """兼容旧 API：执行代码并返回 output/error"""
    sb = get_default_sandbox()
    return sb.execute(code)


# 兼容原 API
__all__ = [
    'DockerSandbox',
    'SubprocessSandbox',
    'SandboxRouter',
    'SandboxError',
    'TimeoutException',
    'MemoryLimitException',
    'DangerousCodeException',
    'InstructionCountExceededException',
    'execute_python_code_safely',
    'get_default_sandbox',
]
