#!/usr/bin/env python
# -*- coding: utf-8 -*-

from gevent import monkey
monkey.patch_all()

from bottle import Bottle, run, request, static_file
import adb

app = Bottle()
app.config.setdefault('jobs.home', '/home/pi')


@app.get("/")
def index():
    return 'Hello World!'


@app.get("/key")
def deploy_key():
    '''get the id_rsa.pub key'''
    return static_file('.ssh/id_rsa.pub', root=request.app.config.get('jobs.home'))


@app.get("/devices")
def devices():
    return adb.devices(status=request.params.get("status", "all"))


@app.route("/adb/<cmds:path>")
def adb_cmd(cmds):
    return adb.cmd(cmds.split("/"), timeout=request.params.get("timeout", 10))

from jobs import app as job_app
app.mount("/jobs", job_app)


def main():
    run(app, server='gevent', host='', port='8081', reloader=True)

if __name__ == '__main__':
    main()
