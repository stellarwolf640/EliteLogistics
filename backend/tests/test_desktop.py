import socket
import uuid

from elite_logistics.desktop import LocalApiServer, SingleInstance, find_available_port


def test_available_port_can_be_bound():
    port = find_available_port()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", port))


def test_desktop_server_uses_explicit_loopback_port():
    server = LocalApiServer(port=54321)

    assert server.url == "http://127.0.0.1:54321"


def test_windows_single_instance_mutex_rejects_second_owner():
    name = f"Local\\EliteLogisticsTest-{uuid.uuid4()}"
    first = SingleInstance(name)
    second = SingleInstance(name)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
    finally:
        second.close()
        first.close()
