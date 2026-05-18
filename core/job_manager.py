import threading
from datetime import datetime


JOBS = {}
JOBS_LOCK = threading.Lock()


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_job(title):
    import uuid

    job_id = str(uuid.uuid4())[:8]

    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "title": title,
            "status": "running",
            "logs": [],
            "created_at": now_text(),
            "finished_at": "",
        }

    log(job_id, f"İş başlatıldı: {title}")
    return job_id


def log(job_id, message):
    line = f"[{now_text()}] {message}"
    print(line, flush=True)

    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["logs"].append(line)

            if len(JOBS[job_id]["logs"]) > 3000:
                JOBS[job_id]["logs"] = JOBS[job_id]["logs"][-3000:]


def finish_job(job_id, status="done"):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["status"] = status
            JOBS[job_id]["finished_at"] = now_text()


def get_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        return dict(job)


def list_jobs(limit=8):
    with JOBS_LOCK:
        jobs = list(JOBS.values())[-limit:][::-1]
        return [dict(job) for job in jobs]


def run_thread(target, *args):
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()
