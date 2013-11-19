#!/bin/bash

%if 'branch' in repo:
git clone -b {{repo['branch']}} {{repo['url']}} {{local_repo}}
%else:
git clone {{repo['url']}} {{local_repo}}
%end

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
