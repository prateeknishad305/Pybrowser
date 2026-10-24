from pybroswer.models import FrameTarget, snapshot_from


def test_frame_target_body():
    body = FrameTarget(selector="iframe#x", name="n", url="https://js.stripe.com/**", index=1).to_body()
    assert body["frameSelector"] == "iframe#x"
    assert body["frameName"] == "n"
    assert body["frameUrl"] == "https://js.stripe.com/**"
    assert body["frame"] == 1


def test_snapshot_from_browse():
    shot = snapshot_from(
        {
            "ok": True,
            "sessionId": "abc",
            "id": "abc",
            "title": "T",
            "url": "https://example.com",
            "text": "hi",
            "status": 200,
        }
    )
    assert shot.session_id == "abc"
    assert shot.ok is True
    assert shot.status == 200
