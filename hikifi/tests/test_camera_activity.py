from src.camera_activity import CameraActivityTracker


def test_record_soap_first_then_second() -> None:
    t = CameraActivityTracker(["a", "b"])
    first, st = t.record_soap("a", "192.168.1.5", "GetCapabilities")
    assert first is True
    assert st.soap_requests == 1
    assert st.last_soap_peer == "192.168.1.5"
    first2, st2 = t.record_soap("a", "192.168.1.5", "GetProfiles")
    assert first2 is False
    assert st2.soap_requests == 2


def test_discovery_announce() -> None:
    t = CameraActivityTracker(["x"])
    t.record_discovery_announce("x", "10.0.0.1")
    snap = t.snapshot()["x"]
    assert snap["discoveryAnnouncements"] == 1
    assert snap["lastDiscoveryClient"] == "10.0.0.1"
