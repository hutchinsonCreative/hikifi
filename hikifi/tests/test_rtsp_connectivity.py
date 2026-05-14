from src.rtsp_connectivity import rtsp_tcp_target


def test_rtsp_tcp_target_default_port() -> None:
    h, p = rtsp_tcp_target("rtsp://user:pw@192.168.1.10/stream")
    assert h == "192.168.1.10"
    assert p == 554


def test_rtsp_tcp_target_explicit_port() -> None:
    h, p = rtsp_tcp_target("rtsp://nvr.example:8554/cam")
    assert h == "nvr.example"
    assert p == 8554
