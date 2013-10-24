#!/bin/bash

%python = init.get('python', '2.7')
virtualenv --system-site-packages -p /usr/bin/python{{python}} .venv
source .venv/bin/activate

%for install in init.get('install', {}):
{{!install}}
%end

%for before_script in init.get('before_script', {}):
{{!before_script}}
%end

%for script in init.get('script', {}):
{{!script}}
%end

%for after_script in init.get('after_script', {}):
{{!after_script}}
%end
