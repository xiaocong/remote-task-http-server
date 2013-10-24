#!/usr/bin/env python
# -*- coding: utf-8 -*-

from bottle import Bottle, request, template, abort, static_file
import os
import uuid
import sh
import json
import yaml
from datetime import datetime
import time
import threading
import functools
import psutil
import shutil
import adb

app = Bottle()
app.config.setdefault('jobs.path', '/home/pi/jobs')
app.config.setdefault('jobs.init_script', '.init.yml')

jobs = []  # we are using memory obj, so we MUST get ONE app instance running.

_lock = threading.Lock()


def lock(fn):
    global _lock

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        _lock.acquire()
        try:
            return fn(*args, **kwargs)
        except:
            raise
        finally:
            _lock.release()
    return wrapper


@app.get("/")
@lock
def all_jobs():
    global jobs
    result = {'all': [], 'jobs': []}
    job_path = app.config.get('jobs.path')
    for dirname in os.listdir(job_path):
        json_file = os.path.join(job_path, dirname, 'job.json')
        if os.path.isfile(json_file):
            with open(json_file) as f:
                result['all'].append(json.load(f))
    if jobs:
        result['jobs'] = [job['job_info'] for job in jobs]
    return result


@app.post("/")
@lock
def create_job():
    repo = request.json.get('repo')
    exclusive = request.json.get('exclusive', "True").lower()
    exclusive = exclusive != 'false' and exclusive != '0'
    env = request.json.get('env', {})
    env.setdefault('ANDROID_SERIAL', 'no_device')

    global jobs
    if exclusive and any(job['job_info']['env']['ANDROID_SERIAL'] == env['ANDROID_SERIAL'] and job['job_info']['exclusive'] for job in jobs):
        abort(409, 'A job on device with the same ANDROID_SERIAL is running!')

    if env['ANDROID_SERIAL'] not in adb.devices(status='ok') and env['ANDROID_SERIAL'] != 'no_device':
        abort(404, 'No specified device attached!')

    jobs_path, job_id = app.config.get('jobs.path'), next_job_id()
    job_path = os.path.abspath(os.path.join(jobs_path, job_id))
    workspace = os.path.join(job_path, 'workspace')
    env['WORKSPACE'] = workspace
    env['JOB_ID'] = job_id
    try:
        os.makedirs(workspace)
    except:
        pass
    local_repo = os.path.join(job_path, 'repo')
    job_out = os.path.join(job_path, 'output')
    job_script = os.path.join(job_path, 'run.sh')
    job_info = os.path.join(job_path, 'job.json')
    with open(job_script, "w") as script_f:
        script_f.write(template(
            'run_script',
            repo=repo,
            local_repo=local_repo,
            init_script='%s/%s/init_script/%s' % (
                refine_url(request.url),
                job_id,
                repo.get('init_script', request.app.config.get('jobs.init_script'))
            ),
            env=env
        ))
    proc = sh.bash(job_script, _out=job_out, _bg=True)

    timestamp = time.time()
    result = {
        'repo': repo,
        'job_id': job_id,
        'job_pid': proc.pid,
        'job_path': job_path,
        'env': env,
        'exclusive': exclusive,
        'timestamp': str(timestamp),
        'datetime': str(datetime.fromtimestamp(timestamp))
    }
    job = {'proc': proc, 'job_info': result}
    jobs.append(job)

    def proc_clear():
        @lock
        def check():
            global jobs
            if job and job['proc'].process.alive:
                return True
            else:
                jobs.remove(job)
                return False
        while check():
            time.sleep(1)
    threading.Thread(target=proc_clear).start()

    with open(job_info, 'w') as info_f:
        info_f.write(json.dumps(result, sort_keys=True, indent=2))
    return result


@app.get("/<job_id>/init_script/<script_name>")
def init_script(job_id, script_name):
    return get_init_script(job_id, script_name)


@app.get("/<job_id>/init_script")
def default_init_script(job_id):
    return get_init_script(job_id, request.app.config.get('jobs.init_script'))


def get_init_script(job_id, script_name):
    init_script = os.path.abspath(os.path.join(app.config.get('jobs.path'), job_id, 'repo', script_name))
    with open(init_script, 'r') as f:
        init_json = yaml.load(f.read())
    return template('init_script', init=init_json)


@app.delete("/<job_id>")
@lock
def terminate_job(job_id):
    global jobs
    for job in jobs:
        if job['job_info']['job_id'] == job_id:
            kill_process_and_children(job['job_info']['job_pid'])
            break
    else:
        abort(410, 'The requested job is already dead!')


@app.get("/<job_id>")
def job_info(job_id):
    jobs_path = app.config.get('jobs.path')
    job_path = os.path.abspath(os.path.join(jobs_path, job_id))
    return static_file('job.json', root=job_path)


@app.get("/<job_id>/stream")
def output(job_id):
    last_lines = int(request.params.get('last_lines', 40))
    jobs_path = app.config.get('jobs.path')
    job_path = os.path.abspath(os.path.join(jobs_path, job_id))
    job_out = os.path.join(job_path, 'output')
    job_info = os.path.join(job_path, 'job.json')
    if not os.path.exists(job_out) or not os.path.exists(job_info):
        raise StopIteration
    with open(job_info) as f:
        info = json.load(f)
    for line in sh.tail('--lines=%d' % last_lines, '--pid=%d' % info['job_pid'], '-f', job_out, _iter=True):
        yield line


@app.get("/<job_id>/file/<path:path>")
def download_file(job_id, path):
    jobs_path = app.config.get('jobs.path')
    job_path = os.path.abspath(os.path.join(jobs_path, job_id))
    return static_file(path, root=job_path)


@app.delete("/<job_id>/file")
@lock
def delete_file(job_id):
    global jobs
    jobs_path = app.config.get('jobs.path')
    job_path = os.path.abspath(os.path.join(jobs_path, job_id))
    if any(job_id == job['job_info']['job_id'] for job in jobs):
        abort(409, 'The specified job is running!')
    shutil.rmtree(job_path, ignore_errors=True)


def refine_url(url):
    if '?' in url:
        url = url[:url.find('?')]
    if url[-1] == '/':
        url = url[:-1]
    return url


def kill_process_and_children(pid):
    parent = psutil.Process(pid)
    if parent.is_running():
        for child in parent.get_children(True):
            if child.is_running():
                child.terminate()
        parent.terminate()


def next_job_id():
    return str(uuid.uuid1())
