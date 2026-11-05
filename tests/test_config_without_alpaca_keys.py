"""Research/backtest code must import without broker credentials (Phase 4 §0c.2)."""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _run(code: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ALPACA_")}
    # Stop config.py from filling the keys in from the repo's .env.
    prelude = "import dotenv; dotenv.load_dotenv = lambda *a, **k: False\n"
    return subprocess.run(
        [sys.executable, "-c", prelude + code], cwd=REPO, env=env, capture_output=True, text=True
    )


def test_config_and_research_modules_import_without_keys():
    result = _run(
        "import thesis_engine.config, thesis_engine.alpaca_client, research.adapters.edgar, "
        "research.pipeline; print('ok')"
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_alpaca_client_raises_clear_error_without_keys():
    result = _run(
        "from thesis_engine.alpaca_client import AlpacaClient, MissingAlpacaCredentials\n"
        "try:\n"
        "    AlpacaClient()\n"
        "except MissingAlpacaCredentials as e:\n"
        "    print('raised:', e)\n"
    )
    assert result.returncode == 0, result.stderr
    assert "raised:" in result.stdout
    assert "ALPACA_API_KEY" in result.stdout and "ALPACA_SECRET_KEY" in result.stdout
