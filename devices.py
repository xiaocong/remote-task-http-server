#!/usr/bin/env python
# -*- coding: utf-8 -*-

from bottle import Bottle, request
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
