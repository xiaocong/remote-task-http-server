#!/bin/bash

%if 'branch' in repo:
CMD="git clone -b {{repo['branch']}} {{repo['url']}} {{local_repo}}"
%else:
CMD="git clone {{repo['url']}} {{local_repo}}"
%end
expect -c "
  set timeout 30;
  spawn $CMD
  expect {
    \"Are you sure you want to continue connecting (yes/no)?*\" {send \"yes\r\";}
    \"password:\" {send \"{{repo.get('password', '')}}\r\";}
  }
  expect eof
"

rc=$?
if [[ $rc != 0 ]] ; then
    echo "Error during download repo!"
    exit $rc
fi

cd {{local_repo}}

%for key in env:
export {{key}}={{env[key]}}
%end

curl {{init_script}} | bash

rc=$?
if [[ $rc != 0 ]] ; then
    exit $rc
fi
