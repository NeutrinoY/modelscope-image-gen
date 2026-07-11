from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def present(tool_name: str, output: BaseModel) -> str:
    data = output.model_dump(mode="json")
    if not data["ok"]:
        error = data["error"]
        lines = [f"[{error['code']}] {error['message']}", f"Retryable: {'yes' if error['retryable'] else 'no'}"]
        job = _job_from_data(data.get("data"))
        if job:
            lines.append(f"Job: {job['job_id']}")
        action = error.get("next_action") or (job.get("next_action") if job else None)
        if error.get("possibly_submitted"):
            lines.append(
                "Next: Do not submit the same request automatically. Review the failed job before creating a new one."
            )
        elif action:
            lines.append(_next_line(action))
        if error.get("provider_request_id"):
            lines.append(f"Provider request: {error['provider_request_id']}")
        return "\n".join(lines)

    payload = data["data"]
    if tool_name == "submit_image_generation":
        job = payload["job"]
        lines = ["Image generation job submitted.", f"Job: {job['job_id']}", f"State: {job['status']}"]
        if job.get("next_action"):
            lines.append(_next_line(job["next_action"]))
        return "\n".join(lines)
    if tool_name == "check_image_generation":
        job = payload["job"]
        if job["status"] == "failed":
            lines = ["Image generation job is in a failed terminal state.", f"Job: {job['job_id']}", "State: failed"]
            if job.get("last_error"):
                lines.extend(
                    [
                        f"Reason: [{job['last_error']['code']}] {job['last_error']['message']}",
                        f"Retryable: {'yes' if job['last_error']['retryable'] else 'no'}",
                    ]
                )
            return "\n".join(lines)
        if job["status"] == "succeeded":
            lines = [
                "Image generation completed upstream.",
                f"Job: {job['job_id']}",
                "State: succeeded",
                f"Artifacts: {job['available_image_count']}/{job['image_count']} available",
            ]
        else:
            lines = ["Image generation is still in progress.", f"Job: {job['job_id']}", f"State: {job['status']}"]
        if job.get("next_action"):
            lines.append(_next_line(job["next_action"]))
        return "\n".join(lines)
    if tool_name == "fetch_image_generation_result":
        return _artifact_text("Image generation artifacts fetched.", payload)
    if tool_name == "generate_image":
        if not payload["completed"]:
            job = payload["job"]
            lines = [
                "Image generation is still running after the local wait limit.",
                f"Job: {job['job_id']}",
                f"State: {job['status']}",
                "Completed: no",
            ]
            if job.get("next_action"):
                lines.append(_next_line(job["next_action"]))
            return "\n".join(lines)
        return _artifact_text("Image generation completed.", payload)
    if tool_name == "list_image_generations":
        items = payload["items"]
        if not items:
            return "No image generation jobs matched the request."
        lines = [f"Image generation jobs: {len(items)}"]
        for item in items:
            next_tool = item["next_action"]["tool"] if item.get("next_action") else "none"
            lines.append(
                f"{item['job_id']} | {item['status']} | artifacts={item['artifact_status']} | "
                f"updated={item['updated_at']} | next={next_tool}"
            )
        lines.append(f"Next cursor: {payload.get('next_cursor') or 'none'}")
        return "\n".join(lines)
    return "Operation completed."


def _artifact_text(title: str, payload: dict[str, Any]) -> str:
    job = payload["job"]
    lines = [
        title,
        f"Job: {job['job_id']}",
        f"State: {job['status']}",
        f"Artifacts: {job['available_image_count']}/{job['image_count']} available",
        f"Partial: {'yes' if payload['partial'] else 'no'}",
    ]
    files = [image["file_path"] for image in payload["images"] if image.get("file_path")]
    if files:
        lines.append("Files:")
        lines.extend(f"- {path}" for path in files)
    if payload["partial"]:
        lines.append("Next: Call fetch_image_generation_result again for the remaining artifacts.")
    return "\n".join(lines)


def _job_from_data(data: dict[str, Any] | None) -> dict[str, Any] | None:
    return data.get("job") if data else None


def _next_line(action: dict[str, Any]) -> str:
    if action["tool"] == "check_image_generation" and action.get("recommended_wait_seconds"):
        return f"Next: Call check_image_generation after about {action['recommended_wait_seconds']} seconds."
    return f"Next: Call {action['tool']}."
