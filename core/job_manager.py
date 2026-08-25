import threading
from datetime import datetime

JOBS = {}
JOBS_LOCK = threading.Lock()


def now_text():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def create_job(title):
    import uuid
    job_id = str(uuid.uuid4())[:8]
    with JOBS_LOCK:
        JOBS[job_id] = {
            'id': job_id,
            'title': title,
            'status': 'running',
            'logs': [],
            'created_at': now_text(),
            'finished_at': '',
            'result_file_path': '',
            'result_file_name': '',
            'result_content_type': 'application/octet-stream',
            'progress_current': 0,
            'progress_total': 0,
            'progress_label': '',
        }
    log(job_id, f'İş başlatıldı: {title}')
    return job_id


def log(job_id, message):
    line = f'[{now_text()}] {message}'
    print(line, flush=True)
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]['logs'].append(line)
            JOBS[job_id]['logs'] = JOBS[job_id]['logs'][-5000:]


def set_progress(job_id, current, total, label=''):
    try:
        current = max(0, int(current))
        total = max(0, int(total))
    except (TypeError, ValueError):
        current, total = 0, 0
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]['progress_current'] = min(current, total) if total else current
            JOBS[job_id]['progress_total'] = total
            JOBS[job_id]['progress_label'] = str(label or '')


def finish_job(job_id, status='done'):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]['status'] = status
            JOBS[job_id]['finished_at'] = now_text()


def set_job_result_file(job_id, file_path, file_name, content_type='application/octet-stream'):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]['result_file_path'] = str(file_path)
            JOBS[job_id]['result_file_name'] = str(file_name)
            JOBS[job_id]['result_content_type'] = str(content_type)


def get_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def list_jobs(limit=10):
    with JOBS_LOCK:
        return [dict(job) for job in list(JOBS.values())[-limit:][::-1]]


def run_thread(target, *args):
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()
