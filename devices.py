#!/usr/bin/env python
# -*- coding: utf-8 -*-

from gevent import spawn
from gevent import subprocess
from bottle import Bottle, request, static_file, abort
import re
import time
import os
from io import BytesIO
try:
    import PIL.Image as Image
except:
    from PIL import Image

from jobs import Lock
import adb

app = Bottle()


@app.get("/")
def devices():
    result = {'android': []}
    good_devices = adb.devices(status='good')
    for se, name in adb.devices(status=request.params.get("status", "all")).items():
        device = {'adb': {'serial': se, 'device': name}}
        if se in good_devices:
            props = adb.getprop(se)
            device.update({
                'product': {
                    'brand': props.get('ro.product.brand'),
                    'manufacturer': props.get('ro.product.manufacturer'),
                    'model': props.get('ro.product.model'),
                    'board': props.get('ro.product.board'),
                    'device': props.get('ro.product.device')
                },
                'locale': {
                    'language': props.get('ro.product.locale.language'),
                    'region': props.get('ro.product.locale.region')
                },
                'build': {
                    'fingerprint': props.get('ro.build.fingerprint'),
                    'type': props.get('ro.build.type'),
                    'date_utc': props.get('ro.build.date.utc'),
                    'display_id': props.get('ro.build.display.id'),
                    'id': props.get('ro.build.id'),
                    'version': {
                        'incremental': props.get('ro.build.version.incremental'),
                        'release': props.get('ro.build.version.release'),
                        'sdk': props.get('ro.build.version.sdk'),
                        'codename': props.get('ro.build.version.codename')
                    }
                }
            })
        result['android'].append(device)
    return result


@app.route("/<serial>/adb/<cmds:path>")
def adb_cmd(serial, cmds):
    return adb.cmd(['-s', serial] + cmds.split("/"), timeout=request.params.get("timeout", 10))


def meminfo(serial):
    result = {}
    for line in adb.cmd(['-s', serial, 'shell', 'cat', '/proc/meminfo'])['stdout'].splitlines():
        item = [i.strip() for i in line.split(':')]
        if len(item) == 2:
            values = item[1].split()
            result[item[0]] = int(values[0])*1024 if len(values) == 2 and values[1] == 'kB' else int(values[0])
    return result


def top(serial):
    result = {"processes": []}
    out = adb.cmd(['-s', serial, 'shell', 'top', '-n', '1'])['stdout']
    m = re.search(r'User\s*(\d+)%,\s*System\s*(\d+)%,\s*IOW\s*(\d+)%,\s*IRQ\s*(\d+)%', out)
    if m:
        result["CPU"] = {
            "User": int(m.group(1)) / 100.,
            "System": int(m.group(2)) / 100.,
            "IOW": int(m.group(3)) / 100.,
            "IRQ": int(m.group(4)) / 100.
        }

    for item in re.findall(r'(\d+)\s+(\d+)\s+(\d+)%\s+(\w+)\s+(\d+)\s+(\d+)K\s+(\d+)K\s+(fg|bg)?\s+(\S+)\s+(\S+)', out):
        pid, pr, cpu, s, thr, vss, rss, pcy, uid, name = item
        result["processes"].append({
            "pid": int(pid),
            "pr": int(pr),
            "cpu": int(cpu) / 100.,
            "s": s,
            "thr": int(thr),
            "vss": int(vss) * 1024,
            "rss": int(rss) * 1024,
            "pcy": pcy,
            "uid": uid,
            "name": name
        })
    return result


@app.get("/<serial>/stat")
def stat(serial):
    return {"meminfo": meminfo(serial), "top": top(serial)}


@app.get("/<serial>/screenshot")
@Lock("screenshot")
def screenshot(serial):
    size = (int(request.params.get('width', 480)), int(request.params.get('height', 480)))
    thumbnail = '%s(%dx%d).thumbnail.png' % (serial, size[0], size[1])
    if not os.path.exists('/tmp/%s' % thumbnail) or time.time() - os.stat('/tmp/%s' % thumbnail).st_mtime > 5:
        p1 = subprocess.Popen(["adb", "-s", serial, "shell", "screencap", "-p"], stdout=subprocess.PIPE)
        p2 = subprocess.Popen(["sed", "s/\r$//"], stdout=subprocess.PIPE, stdin=p1.stdout)
        im = Image.open(BytesIO(p2.communicate()[0]))
        im.thumbnail(size, Image.ANTIALIAS)
        im.save('/tmp/%s' % thumbnail)
    return static_file(thumbnail, root='/tmp')


@app.route("/<serial>/getevent")
def getevent(serial):
    from geventwebsocket import WebSocketError
    wsock = request.environ.get('wsgi.websocket')

    if not wsock:
        abort(400, 'Expected WebSocket request.')

    working = True
    def worker():
        p = subprocess.Popen(["adb", "-s", serial, "shell", "getevent", "-l"], stdout=subprocess.PIPE)
        while working and p.poll() is None:
            line = p.stdout.readline()
            m = re.match(r"/dev/input/event\d+:\s+(EV_KEY\s+KEY_\w+|EV_ABS\s+ABS_MT_TOUCH_MAJOR)\s+\w+", line)
            if m:
                try:
                    wsock.send(m.group(0))
                except WebSocketError:
                    break
        p.kill()

    g = spawn(worker)
    while True:
        try:
            if wsock.receive() is None:
                break
        except WebSocketError:
            break
    working = False
