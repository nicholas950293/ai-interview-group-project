"""沙箱網路阻斷（FR-038；憲章原則 VI「必須禁止對外網路存取」）。

對應 contracts/sandbox-runner.md 的「網路阻斷」必測項目，
以及 SC-009「應徵者程式碼成功對外發起網路連線的次數為 0」。
"""

from __future__ import annotations

import pytest

from backend.src.models.question import Language

pytestmark = pytest.mark.security

OUTBOUND_HTTP = """
import socket, sys
try:
    s = socket.create_connection(("1.1.1.1", 80), timeout=5)
    print("CONNECTED")
except Exception as exc:
    print("BLOCKED", type(exc).__name__)
"""

DNS_LOOKUP = """
import socket
try:
    print("RESOLVED", socket.gethostbyname("example.com"))
except Exception as exc:
    print("BLOCKED", type(exc).__name__)
"""

HOST_SCAN = """
import socket
opened = []
for host in ("172.17.0.1", "host.docker.internal", "10.0.2.2"):
    for port in (22, 5432, 8000):
        try:
            socket.create_connection((host, port), timeout=2).close()
            opened.append((host, port))
        except Exception:
            pass
print("OPEN", opened)
"""


async def test_outbound_http_connection_fails(run):
    result = await run(OUTBOUND_HTTP, Language.PYTHON)
    assert "CONNECTED" not in result.stdout
    assert "BLOCKED" in result.stdout


async def test_dns_resolution_fails(run):
    result = await run(DNS_LOOKUP, Language.PYTHON)
    assert "RESOLVED" not in result.stdout
    assert "BLOCKED" in result.stdout


async def test_host_ports_are_unreachable(run):
    result = await run(HOST_SCAN, Language.PYTHON)
    assert "OPEN []" in result.stdout, f"不得連上宿主連接埠：{result.stdout}"


async def test_no_network_interface_besides_loopback(run):
    code = """
import os
print(sorted(os.listdir('/sys/class/net')))
"""
    result = await run(code, Language.PYTHON)
    # --network=none 只保留 loopback
    assert "eth0" not in result.stdout
