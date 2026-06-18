"""Tests for CosyVoice TTS server configuration."""
import importlib


def test_bundled_zero_shot_prompt_uses_matching_prompt_text(monkeypatch, tmp_path):
    """Bundled zero-shot prompt audio must include its transcript by default."""
    repo = tmp_path / "CosyVoice"
    asset_dir = repo / "asset"
    asset_dir.mkdir(parents=True)
    (asset_dir / "zero_shot_prompt.wav").write_bytes(b"fake-wav")

    monkeypatch.setenv("COSYVOICE_REPO", str(repo))
    monkeypatch.setenv("COSYVOICE_MODEL_DIR", str(tmp_path / "model"))
    monkeypatch.delenv("TTS_ZERO_SHOT_PROMPT_WAV", raising=False)
    monkeypatch.delenv("TTS_ZERO_SHOT_PROMPT_TEXT", raising=False)

    import tts_server.config as config

    config = importlib.reload(config)

    assert config.ZERO_SHOT_PROMPT_WAV == str(asset_dir / "zero_shot_prompt.wav")
    assert config.ZERO_SHOT_PROMPT_TEXT == "希望你以后能够做的比我还好呦。"
