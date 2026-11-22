# -*- coding: utf-8 -*-
"""稳健版 CONNECT 代理：github.com → 真实 IP（当前 hosts 把域名指向 127.0.0.1）。

要点：
- 大缓冲 + TCP_NODELAY，避免 10MB 级 push 被截断
- 半关闭（SHUT_WR）而不是直接 shutdown 双向，避免掐掉上传
"""
import socket
import sys
import threading
import time

BIND = ("127.0.0.1", 7899)
def _ips(*a):
    return list(a)


ROUTE = {
    "github.com": _ips("20.205.243.166", "140.82.112.3", "140.82.114.3", "140.82.116.3", "140.82.113.3"),
    "api.github.com": _ips("20.205.243.168", "140.82.112.6", "140.82.114.6"),
    "uploads.github.com": _ips("140.82.112.9", "140.82.114.9", "20.205.243.166"),
    "codeload.github.com": _ips("20.205.243.166", "140.82.112.3", "140.82.114.3"),
    "gist.github.com": _ips("20.205.243.166", "140.82.112.3"),
    "objects.githubusercontent.com": _ips("185.199.108.133", "185.199.109.133"),
    "raw.githubusercontent.com": _ips("185.199.108.133", "185.199.109.133"),
    "avatars.githubusercontent.com": _ips("185.199.108.133", "185.199.109.133"),
}
BUF = 1 << 18


def tune(s):
    try:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUF)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, BUF)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except Exception:
        pass


def pipe(src, dst, tag):
    total = 0
    try:
        while True:
            data = src.recv(BUF)
            if not data:
                break
            dst.sendall(data)
            total += len(data)
    except Exception as e:
        print(f"  pipe[{tag}] end: {e} ({total} bytes)", flush=True)
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except Exception:
            pass
    print(f"  pipe[{tag}] done {total} bytes", flush=True)


def handle(conn, addr):
    remote = None
    try:
        head = conn.recv(BUF)
        if not head:
            return
        line = head.split(b"\r\n", 1)[0].decode("latin-1")
        parts = line.split()
        if len(parts) < 3 or parts[0].upper() != "CONNECT":
            conn.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return
        host, _, port = parts[1].rpartition(":")
        port = int(port or 443)
        cands = ROUTE.get(host)
        if not cands:
            infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
            cands = [infos[0][4][0]]
        remote = None
        used = None
        for ip in cands:
            try:
                remote = socket.create_connection((ip, port), timeout=8)
                used = ip
                break
            except Exception:
                continue
        if remote is None:
            raise RuntimeError("all IPs failed: %s" % ",".join(cands))
        ip = used
        remote.settimeout(None)
        tune(conn)
        tune(remote)
        conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        t = threading.Thread(target=pipe, args=(conn, remote, "up"), daemon=True)
        t.start()
        pipe(remote, conn, "down")
        t.join(timeout=5)
    except Exception as e:
        print("handle error:", e, flush=True)
        try:
            conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        except Exception:
            pass
    finally:
        for s in (conn, remote):
            if s:
                try:
                    s.close()
                except Exception:
                    pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(BIND)
    srv.listen(128)
    print("proxy listening", BIND, flush=True)
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
