from __future__ import annotations

import os
import subprocess
import sys


def test_package_import_has_no_runtime_side_effects(tmp_path) -> None:
    data_dir = tmp_path / "runtime"
    env = dict(os.environ)
    env["MODELSCOPE_IMAGE_GEN_DATA_DIR"] = str(data_dir)
    completed = subprocess.run(
        [sys.executable, "-c", "import modelscope_image_gen"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert not data_dir.exists()


def test_cli_version_does_not_require_token() -> None:
    env = dict(os.environ)
    env.pop("MODELSCOPE_SDK_TOKEN", None)
    completed = subprocess.run(
        [sys.executable, "-m", "modelscope_image_gen", "--version"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "0.2.1"
    assert completed.stderr == ""


def test_settings_load_env_local_and_new_default_model(tmp_path, monkeypatch) -> None:
    from modelscope_image_gen.infrastructure.config.settings import Settings

    (tmp_path / ".env.local").write_text("MODELSCOPE_SDK_TOKEN=test-local-token\n", encoding="utf-8")
    monkeypatch.delenv("MODELSCOPE_SDK_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.default_model == "krea/Krea-2-Turbo"
    assert settings.token_value == "test-local-token"
