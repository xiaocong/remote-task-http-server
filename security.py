#!/usr/bin/env python
# -*- coding: utf-8 -*-

from bottle import Bottle, request, static_file

app = Bottle()
app.config.setdefault('user.home', '/home/pi')


@app.get("/key")
def deploy_key():
    '''get the id_rsa.pub key'''
    return static_file('.ssh/id_rsa.pub', root=request.app.config.get('user.home'))
