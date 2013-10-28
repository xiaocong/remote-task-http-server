remote-task-http-server
=======================

The server is to receive request and run the requested task on the server side, which is to control the attached android device.


# Run

-   Run the web server

        gunicorn -c gunicorn.config.py app:app

-   Run the monitor daemon

        sudo mkdir /var/log/monitor_daemon
        sudo chmod 777 /var/log/monitor_daemon
        MONITOR_PORT=<web_port> ZOOKEEPER=<host:port> python ./monitor_daemon.py start
