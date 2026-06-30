"""Host configuration management — read/write ~/.linux-remote/hosts.yaml."""

import os
import yaml
from pathlib import Path
from typing import Optional


def config_dir() -> Path:
    """Return the config directory, creating if needed."""
    p = Path.home() / ".linux-remote"
    p.mkdir(parents=True, exist_ok=True)
    return p


def hosts_file() -> Path:
    return config_dir() / "hosts.yaml"


def load_hosts() -> dict:
    """Load all pre-configured hosts. Returns {alias: host_cfg}."""
    path = hosts_file()
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("hosts", {})


def save_hosts(hosts: dict) -> None:
    """Save the full hosts dict."""
    path = hosts_file()
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"hosts": hosts}, f, default_flow_style=False, allow_unicode=True)


def get_host(alias: str) -> Optional[dict]:
    """Look up a host by alias. Returns None if not found."""
    hosts = load_hosts()
    return hosts.get(alias)


def add_host(alias: str, host: str, port: int = 22, user: str = "root",
             password: Optional[str] = None, key_file: Optional[str] = None,
             key_content: Optional[str] = None) -> None:
    """Add or overwrite a host entry."""
    hosts = load_hosts()
    cfg = {"host": host, "port": port, "user": user}
    if password:
        cfg["password"] = password
    if key_file:
        cfg["key_file"] = os.path.expanduser(key_file)
    if key_content:
        cfg["key_content"] = key_content
    hosts[alias] = cfg
    save_hosts(hosts)


def remove_host(alias: str) -> bool:
    """Remove a host entry. Returns True if it existed."""
    hosts = load_hosts()
    if alias in hosts:
        del hosts[alias]
        save_hosts(hosts)
        return True
    return False


def list_hosts() -> list[dict]:
    """List all pre-configured hosts with alias and basic info."""
    hosts = load_hosts()
    result = []
    for alias, cfg in hosts.items():
        result.append({
            "alias": alias,
            "host": cfg.get("host", ""),
            "port": cfg.get("port", 22),
            "user": cfg.get("user", "root"),
            "auth_type": "key" if ("key_file" in cfg or "key_content" in cfg) else "password",
        })
    return result


def resolve_connection(host_or_alias: str, user: Optional[str] = None,
                       port: Optional[int] = None, password: Optional[str] = None,
                       key_file: Optional[str] = None) -> dict:
    """Resolve a connection target — either a pre-configured alias or ad-hoc params.

    Returns a dict with: host, port, user, password?, key_file?, key_content?
    """
    hosts = load_hosts()
    if host_or_alias in hosts:
        # Pre-configured alias
        cfg = dict(hosts[host_or_alias])
        # Allow overrides from ad-hoc params
        if user:
            cfg["user"] = user
        if port:
            cfg["port"] = port
        if password:
            cfg["password"] = password
            cfg.pop("key_file", None)
            cfg.pop("key_content", None)
        if key_file:
            cfg["key_file"] = os.path.expanduser(key_file)
            cfg.pop("password", None)
            cfg.pop("key_content", None)
        # validate
        if "password" not in cfg and "key_file" not in cfg and "key_content" not in cfg:
            raise ValueError(f"Host alias '{host_or_alias}' has no password or key_file configured.")
        return cfg
    else:
        # Ad-hoc connection
        if password or key_file:
            cfg = {
                "host": host_or_alias,
                "port": port or 22,
                "user": user or "root",
            }
            if password:
                cfg["password"] = password
            if key_file:
                cfg["key_file"] = os.path.expanduser(key_file)
            return cfg
        else:
            raise ValueError(
                f"No pre-configured host named '{host_or_alias}' found, "
                f"and no password or key_file provided for ad-hoc connection."
            )
