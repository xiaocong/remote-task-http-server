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
    result = {'android': []}
    good_devices = adb.devices(status='good')
    for se, name in adb.devices(status=request.params.get("status", "all")).items():
        device = {'adb.serial': se, 'adb.device': name}
        if se in good_devices:
            props = adb.getprop(se)
            device.update({
                'product.brand': props.get('ro.product.brand'),
                'product.manufacturer': props.get('ro.product.manufacturer'),
                'product.model': props.get('ro.product.model'),
                'product.board': props.get('ro.product.board'),
                'product.device': props.get('ro.product.device'),
                'locale.language': props.get('ro.product.locale.language'),
                'locale.region': props.get('ro.product.locale.region'),
                'build.fingerprint': props.get('ro.build.fingerprint'),
                'build.type': props.get('ro.build.type'),
                'build.version.incremental': props.get('ro.build.version.incremental'),
                'build.version.release': props.get('ro.build.version.release'),
                'build.version.sdk': props.get('ro.build.version.sdk'),
                'build.version.codename': props.get('ro.build.version.codename'),
                'build.date.utc': props.get('ro.build.date.utc'),
                'build.display.id': props.get('ro.build.display.id'),
                'build.id': props.get('ro.build.id')
                })
        result['android'].append(device)
    return result


@app.route("/adb/<cmds:path>")
def adb_cmd(cmds):
    return adb.cmd(cmds.split("/"), timeout=request.params.get("timeout", 10))

from jobs import app as job_app
app.mount("/jobs", job_app)


def main():
    run(app, server='gevent', host='', port='8081', reloader=True)

if __name__ == '__main__':
    main()
