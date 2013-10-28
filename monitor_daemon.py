#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import time
import os
import json
import requests
import re
from daemon import runner
from kazoo.client import KazooClient

class App():
    
    def __init__(self):
        self.stdin_path = '/dev/null'
        self.stdout_path = '/dev/tty'
        self.stderr_path = '/dev/tty'
        self.pidfile_path =  '/var/log/monitor_daemon/monitor_daemon.pid'
        self.pidfile_timeout = 5

    def mac_and_ip(self, eth):
        import subprocess
        out = subprocess.Popen(['/sbin/ifconfig', eth], stdout=subprocess.PIPE).communicate()[0].encode('utf-8')
        matches = {
            "ip": r"inet addr:(\d+\.\d+\.\d+\.\d+)",
            "mac": r"Ethernet  HWaddr (\w{2}:\w{2}:\w{2}:\w{2}:\w{2}:\w{2})"
        }
        return dict((k, re.search(matches[k], out).group(1)) for k in matches)

    def run(self):
        server_info = self.mac_and_ip(os.environ.get('MONITOR_INTERFACE', 'eth0'))

        zk_path = '/pi/alive/mac/%s' % server_info['mac']
        zk = KazooClient(hosts=os.environ.get('ZOOKEEPER', 'zookeeper_server:2181'))
        zk.start()
        zk.create(zk_path, json.dumps(server_info), ephemeral=True, makepath=True)
        while True:
            try:
                server_info['web'] = {'port': int(os.environ.get('MONITOR_PORT', 80))}
                url = 'http://%s:%d' % (server_info['ip'], server_info['web']['port'])

                try:
                    if requests.get('%s/api/ping' % url).status_code == 200:
                        server_info['web']['status'] = 'up'
                except:
                    server_info['web']['status'] = 'down'
                else:
                    devices = requests.get('%s/api/0/devices' % url)
                    if devices.status_code == 200:
                        server_info['web']['devices'] = devices.json()
                    else:
                        server_info['web']['devices'] = {}

                    jobs = requests.get('%s/api/0/jobs' % url, params={'all': False})
                    if jobs.status_code == 200:
                        server_info['web']['jobs'] = jobs.json()['jobs']
                    else:
                        server_info['web']['jobs'] = []

                data, stat = zk.get(zk_path)
                if data and json.loads(data) != server_info:
                    value = json.dumps(server_info)
                    zk.set(zk_path, value)
                    logger.info('Update ZK %s: %s' % (zk_path, value))
            except Exception as e:
                logger.error(e.strerror)
            time.sleep(3)

app = App()
logger = logging.getLogger("DaemonLog")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.FileHandler("/var/log/monitor_daemon/monitor_daemon.log")
handler.setFormatter(formatter)
logger.addHandler(handler)

daemon_runner = runner.DaemonRunner(app)
#This ensures that the logger file handle does not get closed during daemonization
daemon_runner.daemon_context.files_preserve=[handler.stream]
daemon_runner.do_action()
