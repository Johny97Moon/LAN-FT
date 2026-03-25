"""
UDP broadcast discovery.
Sender broadcasts DISCOVER on port DISCOVERY_PORT.
Any host running start_discovery_responder() replies with its hostname + TCP port.
"""
import json
import socket
import threading
import time
from typing import Callable

try:
    from zeroconf import IPVersion, ServiceInfo, Zeroconf, ServiceBrowser
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False

from services.ip_service import get_local_ip

DISCOVERY_PORT = 5002
BROADCAST_ADDR = "255.255.255.255"
MAGIC = "LAN-FT-DISCOVER"
SERVICE_TYPE = "_lan-ft._tcp.local."


def broadcast_discover(tcp_port: int, timeout: float = 2.0) -> list[dict]:
    """
    Send a broadcast and collect responses.
    Returns list of {"ip": ..., "hostname": ..., "port": ...}
    """
    results: list[dict] = []
    seen: set[str] = set()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(timeout)
        msg = json.dumps({"magic": MAGIC, "tcp_port": tcp_port}).encode()
        s.sendto(msg, (BROADCAST_ADDR, DISCOVERY_PORT))

        deadline = _now() + timeout
        while _now() < deadline:
            try:
                data, addr = s.recvfrom(1024)
                resp = json.loads(data.decode())
                if resp.get("magic") == MAGIC + "-REPLY" and addr[0] not in seen:
                    seen.add(addr[0])
                    results.append({
                        "ip": addr[0],
                        "hostname": resp.get("hostname", addr[0]),
                        "port": resp.get("port", tcp_port),
                    })
            except socket.timeout:
                break
            except Exception:
                continue

    # ── Zeroconf discovery ─────────────────────────────────────────
    if ZEROCONF_AVAILABLE:
        zc = Zeroconf()
        try:
            browser_listener = _ZCSenderListener(results, seen, tcp_port)
            ServiceBrowser(zc, SERVICE_TYPE, browser_listener)
            
            # Wait for both UDP broadcast and Zeroconf within the same timeout
            time_left = deadline - _now()
            if time_left > 0:
                time.sleep(time_left)
        finally:
            zc.close()

    return results


class _ZCSenderListener:
    def __init__(self, results, seen, target_port):
        self.results = results
        self.seen = seen
        self.target_port = target_port

    def add_service(self, zc: "Zeroconf", type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info and info.addresses:
            ip = socket.inet_ntoa(info.addresses[0])
            if ip not in self.seen:
                self.seen.add(ip)
                # hostname clean: remove .local. and _lan-ft._tcp.local.
                host_clean = info.server.split(".")[0]
                self.results.append({
                    "ip": ip,
                    "hostname": host_clean,
                    "port": info.port,
                })

    def update_service(self, zc: "Zeroconf", type_: str, name: str) -> None:
        pass

    def remove_service(self, zc: "Zeroconf", type_: str, name: str) -> None:
        pass


def start_discovery_responder(
    tcp_port: int,
    stop_event: threading.Event,
) -> None:
    """Listen for broadcast DISCOVER messages and reply + start Zeroconf."""
    hostname = socket.gethostname()
    
    # Start Zeroconf in a separate thread BEFORE entering the UDP loop
    zc_thread = threading.Thread(
        target=_run_zc_responder, args=(tcp_port, stop_event), daemon=True
    )
    zc_thread.start()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("", DISCOVERY_PORT))
        except Exception:
            # Maybe port taken by another instance
            return
        s.settimeout(1.0)

        while not stop_event.is_set():
            try:
                data, addr = s.recvfrom(1024)
                req = json.loads(data.decode())
                if req.get("magic") != MAGIC:
                    continue
                reply = json.dumps({
                    "magic": MAGIC + "-REPLY",
                    "hostname": hostname,
                    "port": tcp_port,
                }).encode()
                s.sendto(reply, addr)
            except (socket.timeout, json.JSONDecodeError, UnicodeDecodeError):
                continue
            except Exception:
                continue


def _run_zc_responder(tcp_port: int, stop_event: threading.Event):
    if not ZEROCONF_AVAILABLE:
        return
    
    hostname = socket.gethostname()
    local_ip = get_local_ip()
    if not local_ip: return

    # Use unique name for Zeroconf to avoid collisions
    info = ServiceInfo(
        SERVICE_TYPE,
        f"{hostname}-{tcp_port}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(local_ip)],
        port=tcp_port,
        server=f"{hostname}.local.",
    )
    # Instantiate Zeroconf only once per responder session
    zc = Zeroconf()
    zc.register_service(info)
    try:
        while not stop_event.is_set():
            stop_event.wait(1.0)
    finally:
        try:
            zc.unregister_service(info)
            zc.close()
        except Exception:
            pass




def _now() -> float:
    return time.monotonic()
