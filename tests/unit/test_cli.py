from story_teller.cli import main


def test_generate_prints_review_url(monkeypatch, capsys):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"id": "abc123"}

    monkeypatch.setattr("story_teller.cli.httpx.post", lambda *args, **kwargs: Response())
    assert main(["generate", "--theme", "betrayal"]) == 0
    assert "http://127.0.0.1:8765" in capsys.readouterr().out
