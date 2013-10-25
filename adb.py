#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sh import adb
from time import sleep
import re


def devices(status='all'):
    out = adb.devices().stdout.encode('utf-8')
    match = "List of devices attached"
    index = out.find(match)
    error_statuses = ['offline', 'no permissions']
    if index < 0:
        return {}
    else:
        all = dict([s.split('\t') for s in out[index + len(match):].strip().splitlines() if s.strip()])
        if status in error_statuses:
            return dict(filter(lambda pair: pair[1] == status, all.items()))
        elif status in ['error', 'err', 'bad']:
            return dict(filter(lambda pair: pair[1] in error_statuses, all.items()))
        elif status in ['ok', 'ready', 'good', 'alive']:
            return dict(filter(lambda pair: pair[1] not in error_statuses, all.items()))
        elif status == 'all':
            return all
        else:
            return {}


def cmd(cmds, **kwargs):
    proc = adb(*cmds, _bg=True)
    start, interval, timeout = 0, 0.1, int(kwargs.get('timeout', 10))
    while start < timeout:
        sleep(interval)
        start += interval
        if not proc.process.alive:
            break
    else:
        proc.kill()
    try:
        proc.wait()
    except:
        pass
    return {
        'stdout': proc.stdout,
        'stderr': proc.stderr,
        'returncode': proc.exit_code
    }


def getprop(serial, prop=None):
    if prop:
        return cmd(['-s', serial, 'shell', 'getprop', prop])['stdout'].strip()
    else:
        out = cmd(['-s', serial, 'shell', 'getprop'])['stdout']
        return dict(re.findall(r"\[([^[\]]+)\]: +\[([^[\]]+)\]", out.encode('utf-8')))
