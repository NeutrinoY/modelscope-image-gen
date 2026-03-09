from __future__ import annotations

from modelscope_image_gen.task_store import TaskStore


def test_task_store_save_and_load_roundtrip(tmp_path) -> None:
    store = TaskStore(state_dir=str(tmp_path / "jobs"))
    payload = {
        "job_id": "job_1",
        "state": "submitted",
        "task_id": "task_1",
    }

    store.save(payload)
    loaded = store.load("job_1")

    assert loaded is not None
    assert loaded["job_id"] == "job_1"
    assert loaded["task_id"] == "task_1"


def test_task_store_returns_none_for_missing_job(tmp_path) -> None:
    store = TaskStore(state_dir=str(tmp_path / "jobs"))

    assert store.load("missing") is None
