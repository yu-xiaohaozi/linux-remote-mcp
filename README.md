# 🖥️ linux-remote MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Server-green)](https://modelcontextprotocol.io/)

通过 SSH 远程控制 Linux 机器的 MCP Server。**35 个工具**，覆盖会话管理、文件传输、系统运维、Docker 管理和 CTF 攻防场景。支持同时连接多台机器，自动适配不同发行版。

---

## 🚀 快速开始

### 1. 安装

```bash
git clone https://github.com/yu-xiaohaozi/linux-remote-mcp.git
cd linux-remote-mcp
pip install -e .
```

### 2. 配置 MCP 客户端

**Claude Desktop** (`claude_desktop_config.json`)：

```json
{
  "mcpServers": {
    "linux-remote": {
      "command": "python",
      "args": ["-m", "linux_remote"]
    }
  }
}
```

**Reasonix / 其他支持 MCP 的客户端**：直接将上述配置加入你的 `config.toml` 或 `.mcp.json`。

### 3. 开始使用

```
→ session_connect(target="192.168.1.100", user="root", password="xxx")
✅ Connected to root@192.168.1.100:22 [sess-1]

→ sys_info(session_id="sess-1")
CentOS 7 / 3.10.0 kernel / 4GB RAM / 50GB disk

→ pkg_install(session_id="sess-1", packages="nginx docker.io")
✅ Installed via yum
```

---

## ✨ 特性

| 特性 | 说明 |
|------|------|
| 🔌 **SSH 会话池** | 持久连接，支持同时管理多台机器 |
| 🧠 **智能适配** | 自动识别 apt/yum/dnf/pacman、systemd/sysvinit、ufw/firewalld |
| 🔐 **双模式认证** | 密码登录 + SSH 密钥，临时传参或预配置别名 |
| 🎯 **CTF 专用** | 反弹 Shell 生成、端口扫描、一键 HTTP 服务、nc 监听 |
| 🐳 **Docker 管理** | 容器启停、日志查看、容器内命令执行 |
| 📦 **开箱即用** | pip install 一条命令，无需额外配置 |

---

## 🏗️ 架构

```
┌──────────────┐     MCP Protocol     ┌──────────────────┐     SSH      ┌────────────┐
│  AI Agent    │ ◄────────────────── ► │  linux-remote    │ ◄────────── ► │  Linux VM  │
│ (Claude etc) │     (stdio/JSON-RPC)  │  MCP Server      │  (asyncssh)  │  (任意发行版) │
└──────────────┘                       └──────────────────┘              └────────────┘
                                              │
                                        ~/.linux-remote/
                                         hosts.yaml (可选)
```

### 持久会话 vs 短连接

每个 `session_connect` 创建一个**持久 SSH 会话**，后续所有操作通过 `session_id` 引用。支持**同时持有多个会话**，在多台机器间自由切换。调用 `session_disconnect` 或进程退出时自动清理。

---

## 📋 工具参考

### 🔌 会话管理 (3)

| 工具 | 参数 | 说明 |
|------|------|------|
| `session_connect` | `target`, `user?`, `port?`, `password?`, `key_file?`, `session_id?` | 连接主机（IP 或预配置别名） |
| `session_disconnect` | `session_id` | 断开指定会话 |
| `session_list` | — | 列出所有活跃会话及运行时长 |

### ⚡ 命令 & 文件 (6)

| 工具 | 参数 | 说明 |
|------|------|------|
| `exec` | `session_id`, `command`, `timeout?` | 执行任意 Shell 命令 |
| `file_upload` | `session_id`, `local_path`, `remote_path` | 上传文件 (SFTP) |
| `file_download` | `session_id`, `remote_path`, `local_path` | 下载文件 (SFTP) |
| `file_write` | `session_id`, `remote_path`, `content`, `mode?` | 写入文件内容 |
| `file_read` | `session_id`, `remote_path`, `max_bytes?` | 读取文件内容 |
| `file_exists` | `session_id`, `path` | 检查文件/目录是否存在 |

### 🗂️ 主机配置 (3)

| 工具 | 参数 | 说明 |
|------|------|------|
| `host_add` | `alias`, `host`, `port?`, `user?`, `password?`, `key_file?` | 保存主机别名 |
| `host_remove` | `alias` | 删除主机别名 |
| `host_list` | — | 列出所有已保存的主机 |

### 🖥️ 系统管理 (11)

| 工具 | 参数 | 说明 |
|------|------|------|
| `sys_info` | `session_id` | 系统概览（OS/内核/CPU/内存/磁盘） |
| `sys_users` | `session_id` | 列出 uid≥1000 的用户 |
| `pkg_install` | `session_id`, `packages` | 安装软件包（自动识别包管理器） |
| `pkg_update` | `session_id` | 更新所有系统包 |
| `pkg_list` | `session_id`, `filter?` | 列出已安装包（支持过滤） |
| `svc_manage` | `session_id`, `service`, `action` | 启停服务（start/stop/restart/enable/disable/status） |
| `svc_list` | `session_id` | 列出运行中的服务 |
| `proc_list` | `session_id`, `sort_by?`, `count?` | 进程列表（按 CPU/内存排序） |
| `proc_kill` | `session_id`, `pid`, `signal?` | 终止进程 |
| `user_add` | `session_id`, `username`, `password?`, `sudo?` | 创建用户（可选密码+sudo） |
| `user_del` | `session_id`, `username` | 删除用户及家目录 |

### 🌐 网络 (3)

| 工具 | 参数 | 说明 |
|------|------|------|
| `port_check` | `session_id`, `port` | 检查端口是否监听及归属进程 |
| `port_listen` | `session_id` | 列出所有监听 TCP 端口 |
| `firewall_allow` | `session_id`, `port`, `protocol?` | 开放防火墙端口（ufw/firewalld/iptables） |

### 🐳 Docker (5)

| 工具 | 参数 | 说明 |
|------|------|------|
| `docker_ps` | `session_id`, `all?` | 列出容器 |
| `docker_run` | `session_id`, `image`, `name?`, `ports?`, `env?`, `volume?`, `restart?`, `extra_args?` | 运行容器 |
| `docker_stop` | `session_id`, `container`, `remove?` | 停止（可选删除）容器 |
| `docker_logs` | `session_id`, `container`, `tail?` | 查看容器日志 |
| `docker_exec` | `session_id`, `container`, `command` | 在容器内执行命令 |

### 🚩 CTF 工具 (4)

| 工具 | 参数 | 说明 |
|------|------|------|
| `ctf_serve_http` | `session_id`, `port?`, `directory?` | 一键启动 Python HTTP 文件服务 |
| `ctf_listen_port` | `session_id`, `port`, `protocol?` | nc 监听端口（接收连接/Shell） |
| `ctf_reverse_shell` | `ip`, `port`, `shell_type?` | 生成反弹 Shell 命令（bash/python/nc/php/perl/ruby） |
| `ctf_scan_ports` | `session_id`, `target`, `ports?` | 内网快速端口扫描 |

---

## 📖 使用示例

### 场景一：多机运维

```
# 同时连接 Web 服务器和数据库服务器
session_connect(target="web-prod", user="root", password="xxx")     → sess-1
session_connect(target="db-prod", user="root", password="xxx")      → sess-2

# 在 Web 服务器装 Nginx
pkg_install(session_id="sess-1", packages="nginx")
svc_manage(session_id="sess-1", service="nginx", action="start")

# 在数据库服务器装 MySQL
docker_run(session_id="sess-2", image="mysql:8", name="db",
           ports="3306:3306", env="MYSQL_ROOT_PASSWORD=secret")

# 查看两边状态
exec(session_id="sess-1", command="systemctl status nginx")
docker_ps(session_id="sess-2")
```

### 场景二：CTF 攻防

```
# 连接 Kali 攻击机
session_connect(target="kali-vm")  → sess-1

# 内网扫描目标
ctf_scan_ports(session_id="sess-1", target="192.168.1.50", ports="1-1000")

# 生成反弹 Shell，在你的机器上先开监听
ctf_listen_port(session_id="sess-1", port=4444)
ctf_reverse_shell(ip="10.0.0.1", port=4444, shell_type="python")
# 把生成的 payload 粘贴到目标机器执行

# 快速传文件
ctf_serve_http(session_id="sess-1", port=8080, directory="/tmp/payloads")
```

### 场景三：环境搭建

```
session_connect(target="dev-server", user="root", password="xxx")

# 一键安装开发环境
pkg_install(session_id="sess-1", packages="git python3 nodejs docker.io")
user_add(session_id="sess-1", username="dev", password="dev123", sudo=true)

# 部署服务
docker_run(session_id="sess-1", image="nginx:alpine", name="web", ports="80:80")
firewall_allow(session_id="sess-1", port=80)
```

---

## 🔧 预配置主机

不想每次输入 IP 和密码？用别名保存：

```
host_add(alias="kali", host="192.168.1.50", user="kali", password="your-password")
host_add(alias="centos", host="192.168.1.100", user="root", password="your-password")
```

之后直接 `session_connect(target="kali")` 即可。配置文件存储在 `~/.linux-remote/hosts.yaml`：

```yaml
hosts:
  kali:
    host: 192.168.1.50
    port: 22
    user: kali
    password: your-password
  centos:
    host: 192.168.1.100
    port: 22
    user: root
    password: your-password
```

也支持 SSH 密钥：

```yaml
hosts:
  prod-server:
    host: 10.0.0.5
    user: root
    key_file: ~/.ssh/id_rsa
```

---

## 📦 依赖

| 包 | 用途 |
|---|------|
| `mcp` | MCP 协议框架 |
| `asyncssh` | 异步 SSH 连接池 |
| `pyyaml` | 主机配置文件解析 |

Python ≥ 3.10

---

## 🤝 贡献

欢迎提 Issue 和 PR！如果你有常用的运维操作希望封装成高层工具，请在 Issue 中描述场景。

---

## 📄 License

[MIT](LICENSE)
