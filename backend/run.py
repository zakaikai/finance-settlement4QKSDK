"""Packaged application entry point.

Replaces `uvicorn backend.main:app` CLI.
Handles path resolution for PyInstaller bundles, database setup,
auto-browser launch, single-instance guard, and HTTPS with self-signed cert.
"""
import os
import sys
import socket
import webbrowser
import threading
import json
import datetime
import ipaddress
from pathlib import Path


def get_app_root() -> Path:
    """Return the directory containing the executable (or project root in dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_internal_dir() -> Path:
    """Return _internal/ (PyInstaller) or project root (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return get_app_root()


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def _ensure_ssl_cert(root: Path, lan_ips: list[str]) -> tuple[str, str] | None:
    """Generate a self-signed certificate for HTTPS. Returns (keyfile, certfile).

    Set FINANCE_NO_SSL=true to disable HTTPS entirely.
    Certificate is regenerated only if the files are missing.
    """
    if os.environ.get("FINANCE_NO_SSL", "").strip().lower() == "true":
        return None

    ssl_dir = root / "ssl"
    try:
        ssl_dir.mkdir(exist_ok=True)
    except OSError:
        return None

    key_file = ssl_dir / "key.pem"
    cert_file = ssl_dir / "cert.pem"

    if key_file.exists() and cert_file.exists():
        return str(key_file), str(cert_file)

    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        return None

    # Generate private key
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Build Subject Alternative Names: localhost + 127.0.0.1 + all LAN IPs
    sans = [x509.DNSName("localhost")]
    for ip_str in lan_ips:
        try:
            sans.append(x509.IPAddress(ipaddress.IPv4Address(ip_str)))
        except ValueError:
            pass
    sans.append(x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")))

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Finance Settlement"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Finance"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .sign(private_key, hashes.SHA256())
    )

    with open(key_file, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    try:
        os.chmod(key_file, 0o600)
    except (OSError, NotImplementedError):
        pass  # Windows doesn't support chmod in the same way
    return str(key_file), str(cert_file)


def get_version() -> str:
    for d in (get_app_root(), get_internal_dir()):
        vp = d / "version.json"
        if vp.exists():
            try:
                return json.loads(vp.read_text()).get("version", "1.0.0")
            except Exception:
                return "1.0.0"
    return "1.0.0"


def get_lan_ips() -> list:
    """Return LAN IP addresses (non-loopback IPv4)."""
    import socket
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if not ip.startswith("127.") and ":" not in ip:
                ips.add(ip)
    except Exception:
        pass
    # Fallback: try common LAN prefixes
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
            s.close()
        except Exception:
            pass
    return list(ips)


def main():
    root = get_app_root()
    internal = get_internal_dir()

    # Set FINANCE_ROOT for other modules to discover paths
    os.environ["FINANCE_ROOT"] = str(root)

    # Load user config.env first — variables below may depend on it
    config_env = root / "config.env"
    if config_env.exists():
        from dotenv import load_dotenv
        load_dotenv(config_env)
    elif not getattr(sys, "frozen", False):
        # Dev mode: also check project root .env
        dev_env = Path(__file__).resolve().parent.parent / ".env"
        if dev_env.exists():
            from dotenv import load_dotenv
            load_dotenv(dev_env)

    os.environ.setdefault("FINANCE_PORT", "8770")

    # LAN sharing: if not enabled, bind to localhost only
    lan_enabled = os.environ.get("LAN_ENABLED", "false").strip().lower() == "true"
    os.environ["FINANCE_HOST"] = "0.0.0.0" if lan_enabled else "127.0.0.1"

    # Ensure data directory exists next to the exe
    data_dir = root / "data"
    data_dir.mkdir(exist_ok=True)

    # Set database path
    db_path = os.environ.get("DB_PATH", "").strip()
    if not db_path:
        db_path = str(data_dir / "settlement.db")
        os.environ["DB_PATH"] = db_path
    else:
        if not os.path.isabs(db_path):
            db_path = str(root / db_path)
            os.environ["DB_PATH"] = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Set asset paths for the backend modules
    frontend_dist = internal / "frontend" / "dist"
    if frontend_dist.exists():
        os.environ["FRONTEND_DIST"] = str(frontend_dist)
    else:
        # Dev fallback
        dev_dist = root / "frontend" / "dist"
        if dev_dist.exists():
            os.environ["FRONTEND_DIST"] = str(dev_dist)

    templates_dir = internal / "templates"
    if templates_dir.exists():
        os.environ["TEMPLATES_DIR"] = str(templates_dir)

    port = int(os.environ["FINANCE_PORT"])
    host = os.environ["FINANCE_HOST"]

    # Set up SSL certificate
    lan_ips = get_lan_ips()
    ssl = _ensure_ssl_cert(root, lan_ips)
    protocol = "https" if ssl else "http"

    # Prevent double-launch
    if is_port_in_use(port, host):
        print(f"  端口 {port} 已被占用，检测到服务已在运行")
        webbrowser.open(f"{protocol}://{host}:{port}")
        print(f"  已打开浏览器: {protocol}://{host}:{port}")
        return

    # Open browser after short delay
    def _open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open(f"{protocol}://{host}:{port}")

    threading.Thread(target=_open_browser, daemon=True).start()

    ver = get_version()
    print(f"  ╔══════════════════════════════════════════════╗")
    print(f"  ║    财务结算系统 v{ver.ljust(21)}║")
    print(f"  ║    本机: {protocol}://localhost:{port}{' ' * (16 - len(protocol))}║")
    if lan_enabled:
        for lan_ip in lan_ips:
            url = f"{protocol}://{lan_ip}:{port}"
            print(f"  ║    局域网: {url}{' ' * (18 - len(url))}║")
    else:
        print(f"  ║    局域网分享: 已关闭                          ║")
    print(f"  ║    数据库: {os.path.basename(db_path):30s}║")
    if ssl:
        print(f"  ║    HTTPS: 已启用 (自签名证书)                 ║")
    print(f"  ║    关闭此窗口停止服务                        ║")
    print(f"  ╚══════════════════════════════════════════════╝")

    # Start uvicorn programmatically
    sys.path.insert(0, str(root))
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        ssl_keyfile=ssl[0] if ssl else None,
        ssl_certfile=ssl[1] if ssl else None,
        log_config=None,
        reload=False,
    )


if __name__ == "__main__":
    main()
