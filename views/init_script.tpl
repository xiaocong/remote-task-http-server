#!/bin/bash

%python = init.get('python', '2.7')
virtualenv --system-site-packages -p /usr/bin/python{{python}} .venv
if [ "$?" -ne "0" ]; then
  echo "Error during creating virtual environment!"
  exit 1
fi
source .venv/bin/activate

%for install in init.get('install', {}):
{{!install}}
if [ "$?" -ne "0" ]; then
  echo "Error during installing packages!"
  exit 1
fi
%end

frc=0
%for before_script in init.get('before_script', {}):
{{!before_script}}
%end

%for script in init.get('script', {}):
{{!script}}
rc=$?
if [[ $rc != 0 ]] ; then
    $frc=$rc
fi
%end

%for after_script in init.get('after_script', {}):
{{!after_script}}
%end

exit $frc
