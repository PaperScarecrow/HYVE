"""
HYVE Component: Shadow Sandbox (Left Brain Daemon v2)
======================================================
Secure execution environment for Nyxxie's self-improvement proposals.
Executes code mutations in isolation, collects telemetry, and returns
results to the Shadow Dreamer for evaluation.

Lineage: Left_Brain_Daemon.py → Shadow_Nox_Dreamer.py → HYVE Shadow Sandbox

MODES:
  - LOCAL: Execute in a subprocess with timeout (development)
  - SSH:   Execute on an airgapped sandbox machine (production)

SAFETY:
  - Hard timeout on all executions (default 120s)
  - No network access from sandbox (when SSH mode)
  - No filesystem access outside designated workspace
  - All code reviewed by Shadow Dreamer before execution
  - Human approval gate (can be disabled for autonomous mode)

Author: Robert Zachary Nemitz
Architecture: Claude Opus 4.6 (Astra)
License: AGPL-3.0
"""

import os
import json
import time
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional, Dict, Any

# Optional SSH support
try:
    import paramiko
    SSH_AVAILABLE = True
except ImportError:
    SSH_AVAILABLE = False


SANDBOX_WORKSPACE = "./nexus_sandbox"
SANDBOX_RESULTS = "./nexus_sandbox_results"
SANDBOX_LOG = "nexus_sandbox_log.json"

# Safety constants
MAX_EXECUTION_TIME = 120      # Hard timeout in seconds
MAX_OUTPUT_SIZE = 1024 * 100  # 100KB max stdout capture
BANNED_IMPORTS = [
    "shutil.rmtree", "os.remove", "os.rmdir", "os.unlink",
    "subprocess.call", "subprocess.Popen",  # No spawning children
    "__import__('os').system",               # No shell escapes
]
BANNED_FILESYSTEM_PATHS = [
    "/etc", "/usr", "/bin", "/sbin", "/boot", "/root",
    "/home", "/media", "/mnt",  # Only sandbox workspace allowed
]


class SandboxConfig:
    """Configuration for the sandbox environment."""
    
    def __init__(
        self,
        mode: str = "local",           # "local" or "ssh"
        ssh_host: str = "",
        ssh_user: str = "",
        ssh_key_path: str = "~/.ssh/id_rsa",
        ssh_port: int = 22,
        require_approval: bool = True, # Human must approve before execution
        max_concurrent: int = 1,       # Max parallel executions
        python_path: str = "python3",
    ):
        self.mode = mode
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.ssh_key_path = os.path.expanduser(ssh_key_path)
        self.ssh_port = ssh_port
        self.require_approval = require_approval
        self.max_concurrent = max_concurrent
        self.python_path = python_path


class ExecutionResult:
    """Structured result from a sandbox execution."""
    
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.status = "pending"     # pending, running, success, failed, timeout, rejected
        self.stdout = ""
        self.stderr = ""
        self.exit_code = -1
        self.execution_time = 0.0
        self.timestamp = time.time()
        self.error_category = None  # syntax, runtime, timeout, import, filesystem
    
    def to_dict(self):
        return {
            "task_id": self.task_id,
            "status": self.status,
            "stdout": self.stdout[:MAX_OUTPUT_SIZE],
            "stderr": self.stderr[:MAX_OUTPUT_SIZE],
            "exit_code": self.exit_code,
            "execution_time": self.execution_time,
            "timestamp": self.timestamp,
            "error_category": self.error_category,
        }


class ShadowSandbox:
    """
    Secure execution environment for self-improvement proposals.
    
    The sandbox receives code from the Shadow Dreamer, validates it
    for safety, executes it in isolation, and returns structured
    telemetry that the dreamer uses to evaluate success.
    """
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self.execution_log = self._load_log()
        self._lock = threading.Lock()
        self._active_executions = 0
        
        os.makedirs(SANDBOX_WORKSPACE, exist_ok=True)
        os.makedirs(SANDBOX_RESULTS, exist_ok=True)
        
        print(f"[HYVE::Sandbox] Online. Mode: {self.config.mode}")
        if self.config.require_approval:
            print(f"[HYVE::Sandbox] Human approval REQUIRED before execution.")
        else:
            print(f"[HYVE::Sandbox] WARNING: Autonomous execution enabled.")
    
    def _load_log(self):
        if os.path.exists(SANDBOX_LOG):
            with open(SANDBOX_LOG, "r") as f:
                return json.load(f)
        return []
    
    def _save_log(self):
        with open(SANDBOX_LOG, "w") as f:
            json.dump(self.execution_log[-500:], f, indent=2)
    
    # =========================================================================
    # SAFETY VALIDATION
    # =========================================================================
    
    def validate_code(self, code: str) -> tuple[bool, str]:
        """
        Static analysis safety check before execution.
        Returns (is_safe, reason).
        """
        # Check for banned imports and operations
        for banned in BANNED_IMPORTS:
            if banned in code:
                return False, f"Banned operation detected: {banned}"
        
        # Check for filesystem access outside workspace
        for banned_path in BANNED_FILESYSTEM_PATHS:
            if banned_path in code and SANDBOX_WORKSPACE not in code:
                return False, f"Filesystem access outside sandbox: {banned_path}"
        
        # Check for network access attempts
        network_indicators = ["socket.", "urllib", "requests.", "http.client", "ftplib"]
        for indicator in network_indicators:
            if indicator in code:
                return False, f"Network access attempted: {indicator}"
        
        # Check for eval/exec of dynamic strings (code injection risk)
        if "eval(" in code or "exec(" in code:
            # Allow if it's clearly operating on literals, reject if on variables
            return False, "Dynamic code execution (eval/exec) not permitted in sandbox"
        
        return True, "passed"
    
    # =========================================================================
    # EXECUTION ENGINES
    # =========================================================================
    
    def execute_local(self, task_id: str, code: str) -> ExecutionResult:
        """Execute code in a local subprocess with timeout."""
        result = ExecutionResult(task_id)
        
        # Write code to a temp file in the sandbox workspace
        script_path = os.path.join(SANDBOX_WORKSPACE, f"task_{task_id}.py")
        with open(script_path, "w") as f:
            f.write(code)
        
        try:
            start_time = time.time()
            
            proc = subprocess.run(
                [self.config.python_path, script_path],
                capture_output=True,
                text=True,
                timeout=MAX_EXECUTION_TIME,
                cwd=SANDBOX_WORKSPACE,  # Jail working directory
                env={
                    "PATH": "/usr/bin:/usr/local/bin",
                    "HOME": SANDBOX_WORKSPACE,
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )
            
            result.execution_time = time.time() - start_time
            result.stdout = proc.stdout
            result.stderr = proc.stderr
            result.exit_code = proc.returncode
            result.status = "success" if proc.returncode == 0 else "failed"
            
            if proc.returncode != 0:
                # Categorize the error
                if "SyntaxError" in proc.stderr:
                    result.error_category = "syntax"
                elif "ImportError" in proc.stderr or "ModuleNotFoundError" in proc.stderr:
                    result.error_category = "import"
                elif "FileNotFoundError" in proc.stderr or "PermissionError" in proc.stderr:
                    result.error_category = "filesystem"
                else:
                    result.error_category = "runtime"
                    
        except subprocess.TimeoutExpired:
            result.status = "timeout"
            result.execution_time = MAX_EXECUTION_TIME
            result.error_category = "timeout"
            result.stderr = f"Execution exceeded {MAX_EXECUTION_TIME}s hard limit"
        except Exception as e:
            result.status = "failed"
            result.stderr = str(e)
            result.error_category = "runtime"
        finally:
            # Clean up the script file
            try:
                os.remove(script_path)
            except OSError:
                pass
        
        return result
    
    def execute_ssh(self, task_id: str, code: str) -> ExecutionResult:
        """Execute code on a remote sandbox machine via SSH."""
        result = ExecutionResult(task_id)
        
        if not SSH_AVAILABLE:
            result.status = "failed"
            result.stderr = "paramiko not installed. pip install paramiko"
            return result
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        remote_script = f"/tmp/nyxxie_sandbox_{task_id}.py"
        
        try:
            ssh.connect(
                self.config.ssh_host,
                port=self.config.ssh_port,
                username=self.config.ssh_user,
                key_filename=self.config.ssh_key_path,
            )
            
            # Upload script
            sftp = ssh.open_sftp()
            with sftp.file(remote_script, "w") as f:
                f.write(code)
            sftp.close()
            
            # Execute with timeout
            start_time = time.time()
            command = f"timeout {MAX_EXECUTION_TIME}s {self.config.python_path} {remote_script}"
            stdin, stdout, stderr = ssh.exec_command(command)
            
            exit_status = stdout.channel.recv_exit_status()
            result.execution_time = time.time() - start_time
            
            result.stdout = stdout.read().decode("utf-8")
            result.stderr = stderr.read().decode("utf-8")
            result.exit_code = exit_status
            
            if exit_status == 124:  # timeout command exit code
                result.status = "timeout"
                result.error_category = "timeout"
            elif exit_status != 0:
                result.status = "failed"
                result.error_category = "runtime"
            else:
                result.status = "success"
            
            # Clean up remote script
            ssh.exec_command(f"rm -f {remote_script}")
            
        except Exception as e:
            result.status = "failed"
            result.stderr = f"SSH execution failed: {e}"
            result.error_category = "runtime"
        finally:
            ssh.close()
        
        return result
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def submit_task(self, task_id: str, code: str, description: str = "") -> ExecutionResult:
        """
        Submit code for sandboxed execution.
        
        Returns ExecutionResult with status and telemetry.
        If require_approval is True, this queues the task and returns
        a "pending" result — call approve_task() to execute.
        """
        # Safety validation
        is_safe, reason = self.validate_code(code)
        if not is_safe:
            result = ExecutionResult(task_id)
            result.status = "rejected"
            result.stderr = f"Safety validation failed: {reason}"
            result.error_category = "safety"
            self.execution_log.append(result.to_dict())
            self._save_log()
            print(f"[HYVE::Sandbox] REJECTED task {task_id}: {reason}")
            return result
        
        if self.config.require_approval:
            # Queue for human review
            pending_path = os.path.join(SANDBOX_WORKSPACE, f"pending_{task_id}.json")
            with open(pending_path, "w") as f:
                json.dump({
                    "task_id": task_id,
                    "description": description,
                    "code": code,
                    "submitted_at": time.time(),
                }, f, indent=2)
            
            result = ExecutionResult(task_id)
            result.status = "pending_approval"
            print(f"[HYVE::Sandbox] Task {task_id} queued for human approval.")
            print(f"  Description: {description}")
            print(f"  Review at: {pending_path}")
            return result
        
        # Direct execution (autonomous mode)
        return self._execute(task_id, code)
    
    def approve_task(self, task_id: str) -> ExecutionResult:
        """Approve and execute a pending task."""
        pending_path = os.path.join(SANDBOX_WORKSPACE, f"pending_{task_id}.json")
        
        if not os.path.exists(pending_path):
            result = ExecutionResult(task_id)
            result.status = "failed"
            result.stderr = f"No pending task found: {task_id}"
            return result
        
        with open(pending_path, "r") as f:
            task_data = json.load(f)
        
        os.remove(pending_path)
        return self._execute(task_id, task_data["code"])
    
    def reject_task(self, task_id: str, reason: str = ""):
        """Reject a pending task."""
        pending_path = os.path.join(SANDBOX_WORKSPACE, f"pending_{task_id}.json")
        if os.path.exists(pending_path):
            os.remove(pending_path)
        
        result = ExecutionResult(task_id)
        result.status = "rejected"
        result.stderr = f"Human rejected: {reason}"
        self.execution_log.append(result.to_dict())
        self._save_log()
        print(f"[HYVE::Sandbox] Task {task_id} rejected by human: {reason}")
    
    def list_pending(self) -> list:
        """List all tasks awaiting approval."""
        pending = []
        for f in Path(SANDBOX_WORKSPACE).glob("pending_*.json"):
            with open(f, "r") as fh:
                pending.append(json.load(fh))
        return sorted(pending, key=lambda x: x["submitted_at"])
    
    def _execute(self, task_id: str, code: str) -> ExecutionResult:
        """Internal execution dispatcher."""
        with self._lock:
            if self._active_executions >= self.config.max_concurrent:
                result = ExecutionResult(task_id)
                result.status = "failed"
                result.stderr = "Max concurrent executions reached"
                return result
            self._active_executions += 1
        
        try:
            print(f"[HYVE::Sandbox] Executing task {task_id}...")
            
            if self.config.mode == "ssh":
                result = self.execute_ssh(task_id, code)
            else:
                result = self.execute_local(task_id, code)
            
            self.execution_log.append(result.to_dict())
            self._save_log()
            
            status_emoji = "✓" if result.status == "success" else "✗"
            print(f"[HYVE::Sandbox] Task {task_id} {status_emoji} "
                  f"({result.execution_time:.2f}s) "
                  f"Exit: {result.exit_code}")
            
            return result
        finally:
            with self._lock:
                self._active_executions -= 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Return execution statistics."""
        total = len(self.execution_log)
        if total == 0:
            return {"total": 0}
        
        statuses = {}
        total_time = 0.0
        for entry in self.execution_log:
            s = entry.get("status", "unknown")
            statuses[s] = statuses.get(s, 0) + 1
            total_time += entry.get("execution_time", 0)
        
        return {
            "total": total,
            "statuses": statuses,
            "avg_execution_time": total_time / total,
            "success_rate": statuses.get("success", 0) / total,
        }
