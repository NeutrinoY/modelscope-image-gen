from modelscope_image_gen.domain import ImageId, JobId


def new_job_id() -> JobId:
    return JobId.new()


def new_image_id() -> ImageId:
    return ImageId.new()
