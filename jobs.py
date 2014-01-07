#!/usr/bin/env python
# -*- coding: utf-8 -*-

from bottle import Bottle, request, template, abort, static_file
import os
import uuid
import json
import yaml
from datetime import datetime
import time
from gevent import subprocess, spawn, queue
import threading
import functools
import psutil
import shutil
import adb

app = Bottle()
app.config.setdefault('jobs.path', os.path.join(os.environ['HOME'], 'jobs'))
app.config.setdefault('jobs.init_script', '.init.yml')

jobs = []  # we are using memory obj, so we MUST get ONE app instance running.


class Lock(object):
    locks = {}

    def __init__(self, name):
        self.name = name

    def __call__(self, fn):
        if self.name not in Lock.locks:
            Lock.locks[self.name] = threading.Lock()
        lock = Lock.locks[self.name]

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            lock.acquire()
            try:
                return fn(*args, **kwargs)
            except:
                raise
            finally:
                lock.release()

        return wrapper


@app.get("/")
@Lock("job")
def all_jobs():
    global jobs
    job_path = app.config.get('jobs.path')
    reverse = get_boolean(request.params.get('reverse', 'false'))
    all = get_boolean(request.params.get('all', 'false'))
    result = {}
    if all:
        result['all'] = []
        for dirname in os.listdir(job_path):
            json_file = os.path.join(job_path, dirname, 'job.json')
            if os.path.isfile(json_file):
                with open(json_file) as f:
                    result['all'].append(json.load(f))
    result['jobs'] = [job['job_info'] for job in jobs]

    for key in result:  # sort
        result[key] = sorted(result[key], key=lambda x: float(x['started_at']), reverse=reverse)

    return result


@app.post("/")
def create_job_without_id():
    job_id = request.params.get("job_id") if "job_id" in request.params else next_job_id()
    return create_job(job_id, "%s/%s" % (refine_url(request.url), job_id))


@app.post("/<job_id>")
def create_job_with_id(job_id):
    return create_job(job_id, refine_url(request.url))


@Lock("job")
def create_job(job_id, job_url):
    repo = request.json.get('repo')
    if repo is None:
        abort(400, 'The "repo" is mandatory for creating a new job!')
    exclusive = get_boolean(request.json.get('exclusive', True))
    env = request.json.get('env', {})
    env.setdefault('ANDROID_SERIAL', 'no_device')

    global jobs
    if exclusive and any(job['job_info']['env']['ANDROID_SERIAL'] == env['ANDROID_SERIAL'] and job['job_info']['exclusive'] for job in jobs):
        abort(409, 'A job on device with the same ANDROID_SERIAL is running!')

    if env['ANDROID_SERIAL'] not in adb.devices(status='ok') and env['ANDROID_SERIAL'] != 'no_device':
        abort(404, 'No specified device attached!')

    if any(job['job_info']['job_id'] == job_id for job in jobs):
        abort(409, 'A job with the same job_id is running! If you want to re-run the job, please stop the running one firestly.')

    job_path = os.path.abspath(os.path.join(app.config.get('jobs.path'), job_id))
    shutil.rmtree(job_path, ignore_errors=True)
    workspace = os.path.join(job_path, 'workspace')
    os.makedirs(workspace)  # make the working directory for the job
    env.update({
        'WORKSPACE': workspace,
        'JOB_ID': job_id
    })
    filenames = ['repo', 'output', 'run.sh', 'job.json']
    local_repo, job_out, job_script, job_info = [os.path.join(job_path, f) for f in filenames]
    with open(job_script, "w") as script_f:
        script_f.write(template(
            'run_script',
            repo=repo,
            local_repo=local_repo,
            init_script='%s/init_script/%s' % (
                job_url,
                repo.get('init_script', request.app.config.get('jobs.init_script'))
            ),
            env=env
        ))
    # Start job process
    proc = subprocess.Popen(["/bin/bash", job_script],
                            stdout=subprocess.PIPE,
                            stdin=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    q = queue.Queue() # queue to receive stdour and stderr

    def process_output(stdout, stdin): # process to perform interaction and put output to queue
        out_buf = []
        while True:
            char = stdout.read(1)
            out_buf.append(char)
            line = "".join(out_buf)
            if line.endswith("Are you sure you want to continue connecting (yes/no)? "):
                stdin.write("yes\n")
            elif line.endswith("password: "):
                stdin.write("%s\n" % repo.get("password", ""))
            if char in ["\n", ""]:
                out_buf = []
                q.put(line)
            if char == "":
                q.put(StopIteration)
                break
    def write_output(): # process to receive line from queue and write to file
        with open(job_out, "ab") as f:
            for line in q:
                f.write(line)
                f.flush()
    # spawn processes to perform interaction and write to output file
    spawn(process_output, proc.stdout, proc.stdin)
    spawn(process_output, proc.stderr, proc.stdin)
    spawn(write_output)

    timestamp = time.time()
    result = {
        'repo': repo,
        'job_id': job_id,
        'job_pid': proc.pid,
        'job_path': job_path,
        'env': env,
        'exclusive': exclusive,
        'started_at': str(timestamp),
        'started_datetime': str(datetime.fromtimestamp(timestamp))
    }
    job = {'proc': proc, 'job_info': result}
    jobs.append(job)

    callback = request.json.get('callback')

    def proc_clear():
        @Lock("job")
        def check():
            global jobs
            if job and job['proc'].poll() is None:
                return True
            else:
                jobs.remove(job)
                result['exit_code'] = job['proc'].returncode
                timestamp = time.time()
                result['finished_at'] = str(timestamp)
                result['finished_datetime'] = str(datetime.fromtimestamp(timestamp))
                write_json(job_info, result)
                if callback:
                    import requests
                    try:
                        requests.get(callback,
                                     params={
                                         'job_id': job_id,
                                         'exit_code': result['exit_code']
                                     })
                    except:
                        pass
                return False
        while check():
            time.sleep(1)
    spawn(proc_clear)
    write_json(job_info, result)
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
@app.get("/<job_id>/stop")
@Lock("job")
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
    lines = int(request.params.get('lines', 40))
    jobs_path = app.config.get('jobs.path')
    job_path = os.path.abspath(os.path.join(jobs_path, job_id))
    job_out = os.path.join(job_path, 'output')
    job_info = os.path.join(job_path, 'job.json')
    if not os.path.exists(job_out) or not os.path.exists(job_info):
        raise StopIteration
    with open(job_info) as f:
        info = json.load(f)
    if "exit_code" in info:
        args = ['tail', '--lines=%d' % lines, job_out]
    else:
        args = ['tail', '--lines=%d' % lines, '--pid=%d' % info['job_pid'], '-f', job_out]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for line in p.stdout:
        yield line


@app.get("/<job_id>/files/<path:path>")
def download_file(job_id, path):
    jobs_path = app.config.get('jobs.path')
    job_path = os.path.abspath(os.path.join(jobs_path, job_id))
    if os.path.isdir(os.path.join(job_path, path)):
        return {'files': list_dir(os.path.join(job_path, path))}
    else:
        return static_file(path, root=job_path)


@app.get("/<job_id>/files")
@app.get("/<job_id>/files/")
def list_files(job_id):
    jobs_path = app.config.get('jobs.path')
    job_path = os.path.abspath(os.path.join(jobs_path, job_id))
    if not os.path.exists(job_path):
        abort(404, 'Oh, no! The requested path does not exists!')
    return {'files': list_dir(job_path)}


@app.delete("/<job_id>/files")
@app.get("/<job_id>/remove_files")
@Lock("job")
def delete_file(job_id):
    global jobs
    jobs_path = app.config.get('jobs.path')
    job_path = os.path.abspath(os.path.join(jobs_path, job_id))
    if any(job_id == job['job_info']['job_id'] for job in jobs):
        abort(409, 'The specified job is running!')
    elif not os.path.exists(job_path):
        abort(400, 'No specified job!')
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


def get_boolean(param):
    return param if isinstance(param, bool) else param not in ['false', '0', 0, 'False']


def write_json(filename, obj):
    with open(filename, 'w') as info_f:
        info_f.write(json.dumps(obj, sort_keys=True, indent=2))


def list_dir(path):
    if not os.path.exists(path) or not os.path.isdir(path):
        return None

    result = []
    for f in os.listdir(path):
        filename = os.path.join(path, f)
        stat = os.stat(filename)
        result.append({
            'name': f,
            'is_dir': os.path.isdir(filename),
            'create_time': stat.st_ctime,
            'modify_time': stat.st_mtime,
            'size': stat.st_size
        })
    return result
