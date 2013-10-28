#!/usr/bin/env python
# -*- coding: utf-8 -*-

from bottle import Bottle, run

app = Bottle()


@app.get("/api/ping")
def ping():
    return "pong"

from jobs import app as job_app
app.mount("/api/0/jobs", job_app)

from devices import app as device_app
app.mount("/api/0/devices", device_app)

from security import app as security_app
app.mount("/api/0/security", security_app)


def main():
    run(app, host='', port='8081', reloader=True)

if __name__ == '__main__':
    main()
