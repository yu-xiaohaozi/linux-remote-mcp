"""SSH session manager — connection pool with persistent sessions."""

import asyncio
import asyncssh
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class Session:
    """A single SSH session."""
    session_id: str
    host: str
    port: int
    user: str
    conn: asyncssh.SSHClientConnection
    created_at: float = field(default_factory=lambda: __import__("time").time())


class SessionManager:
    """Manages a pool of concurrent SSH connections."""

    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self._counter: int = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"sess-{self._counter}"

    async def connect(self, host: str, port: int = 22, user: str = "root",
                      password: Optional[str] = None,
                      key_file: Optional[str] = None,
                      key_content: Optional[str] = None,
                      session_id: Optional[str] = None) -> Session:
        """Establish a new SSH connection and track it. Returns the Session."""
        if session_id and session_id in self.sessions:
            raise ValueError(f"Session '{session_id}' already exists. Disconnect it first or use a different ID.")

        sid = session_id or self._next_id()

        connect_kwargs = {
            "host": host, "port": port, "username": user, "known_hosts": None,
        }

        if key_content:
            key_obj = asyncssh.import_private_key(key_content)
            connect_kwargs["client_keys"] = [key_obj]
        elif key_file:
            connect_kwargs["client_keys"] = [key_file]
        elif password:
            connect_kwargs["password"] = password
        else:
            raise ValueError("One of password, key_file, or key_content must be provided.")

        try:
            conn = await asyncio.wait_for(
                asyncssh.connect(**connect_kwargs),
                timeout=15,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Connection to {host}:{port} timed out (15s).")
        except asyncssh.Error as e:
            raise ConnectionError(f"SSH connection to {host}:{port} failed: {e}")

        session = Session(session_id=sid, host=host, port=port, user=user, conn=conn)
        self.sessions[sid] = session
        return session

    async def disconnect(self, session_id: str) -> bool:
        """Disconnect and remove a session. Returns True if it existed."""
        session = self.sessions.pop(session_id, None)
        if session:
            session.conn.close()
            try:
                await asyncio.wait_for(session.conn.wait_closed(), timeout=5)
            except Exception:
                pass
            return True
        return False

    async def disconnect_all(self) -> int:
        """Disconnect all sessions. Returns count."""
        count = len(self.sessions)
        tasks = [self.disconnect(sid) for sid in list(self.sessions.keys())]
        await asyncio.gather(*tasks, return_exceptions=True)
        return count

    def get(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    def require(self, session_id: str) -> Session:
        """Get a session or raise."""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found. Use session_list to see active sessions.")
        return session

    def list_sessions(self) -> list[dict]:
        """List all active sessions with info."""
        import time
        result = []
        for sid, sess in self.sessions.items():
            result.append({
                "session_id": sid,
                "host": sess.host,
                "port": sess.port,
                "user": sess.user,
                "uptime_seconds": round(time.time() - sess.created_at, 1),
            })
        return result

    async def exec(self, session_id: str, command: str, timeout: int = 30) -> dict:
        """Execute a command on a remote session. Returns {stdout, stderr, exit_code}."""
        session = self.require(session_id)
        try:
            result = await asyncio.wait_for(
                session.conn.run(command, encoding="utf-8"),
                timeout=timeout,
            )
            return {
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "exit_code": result.exit_status if result.exit_status is not None else -1,
            }
        except asyncio.TimeoutError:
            return {"stdout": "", "stderr": f"Command timed out after {timeout}s", "exit_code": -1}
        except asyncssh.Error as e:
            return {"stdout": "", "stderr": f"SSH error: {e}", "exit_code": -1}

    async def file_exists(self, session_id: str, path: str) -> dict:
        """Check if a file or directory exists."""
        session = self.require(session_id)
        # Use test command for reliability
        result = await self.exec(session_id, f"test -e '{path}' && echo 'EXISTS' || echo 'NOT_EXISTS'")
        exists = "EXISTS" in result.get("stdout", "")
        # Determine type
        if exists:
            r2 = await self.exec(session_id, f"[ -f '{path}' ] && echo 'FILE' || ([ -d '{path}' ] && echo 'DIR' || echo 'OTHER')")
            ftype = r2.get("stdout", "").strip()
        else:
            ftype = "none"
        return {"exists": exists, "type": ftype, "path": path}

    async def upload(self, session_id: str, local_path: str, remote_path: str) -> dict:
        """Upload a file via SFTP."""
        session = self.require(session_id)
        try:
            async with session.conn.start_sftp_client() as sftp:
                await asyncio.wait_for(
                    sftp.put(local_path, remote_path),
                    timeout=60,
                )
            # Verify
            check = await self.file_exists(session_id, remote_path)
            return {
                "success": check["exists"],
                "local_path": local_path,
                "remote_path": remote_path,
                "message": f"Uploaded {local_path} → {remote_path}" if check["exists"] else "Upload verification failed",
            }
        except asyncio.TimeoutError:
            return {"success": False, "local_path": local_path, "remote_path": remote_path,
                    "message": "Upload timed out (60s)"}
        except Exception as e:
            return {"success": False, "local_path": local_path, "remote_path": remote_path,
                    "message": f"Upload failed: {e}"}

    async def download(self, session_id: str, remote_path: str, local_path: str) -> dict:
        """Download a file via SFTP."""
        session = self.require(session_id)
        try:
            async with session.conn.start_sftp_client() as sftp:
                await asyncio.wait_for(
                    sftp.get(remote_path, local_path),
                    timeout=60,
                )
            return {
                "success": True,
                "local_path": local_path,
                "remote_path": remote_path,
                "message": f"Downloaded {remote_path} → {local_path}",
            }
        except asyncio.TimeoutError:
            return {"success": False, "local_path": local_path, "remote_path": remote_path,
                    "message": "Download timed out (60s)"}
        except Exception as e:
            return {"success": False, "local_path": local_path, "remote_path": remote_path,
                    "message": f"Download failed: {e}"}

    async def write_file(self, session_id: str, remote_path: str, content: str, mode: int = 0o644) -> dict:
        """Write content to a remote file via SFTP."""
        session = self.require(session_id)
        try:
            async with session.conn.start_sftp_client() as sftp:
                import tempfile
                import os as _os
                fd, tmp = tempfile.mkstemp()
                try:
                    with open(fd, "w", encoding="utf-8") as f:
                        f.write(content)
                    await asyncio.wait_for(
                        sftp.put(tmp, remote_path),
                        timeout=30,
                    )
                    await self.exec(session_id, f"chmod {mode:o} '{remote_path}'")
                finally:
                    _os.unlink(tmp)
            return {"success": True, "remote_path": remote_path, "message": f"Written {len(content)} bytes to {remote_path}"}
        except Exception as e:
            return {"success": False, "remote_path": remote_path, "message": f"Write failed: {e}"}

    async def read_file(self, session_id: str, remote_path: str, max_bytes: int = 102400) -> dict:
        """Read a remote file's content via SFTP."""
        session = self.require(session_id)
        try:
            async with session.conn.start_sftp_client() as sftp:
                content_bytes = await asyncio.wait_for(
                    sftp.read(remote_path, offset=0, length=max_bytes),
                    timeout=30,
                )
                # Try to decode as text
                content = content_bytes.decode("utf-8", errors="replace")
            return {
                "success": True,
                "remote_path": remote_path,
                "content": content,
                "size": len(content_bytes),
                "truncated": len(content_bytes) >= max_bytes,
            }
        except Exception as e:
            return {"success": False, "remote_path": remote_path, "content": "", "message": f"Read failed: {e}"}


# Global singleton
_manager: Optional[SessionManager] = None


def get_manager() -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager
