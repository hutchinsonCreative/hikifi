from src.utils.redact import redact_rtsp_url


def test_redact_password() -> None:
    u = redact_rtsp_url("rtsp://admin:secret@192.168.1.2:554/path")
    assert "****" in u
    assert "secret" not in u
    assert "admin" in u
