#!/bin/sh
# Simple wrapper around pyinstaller

set -e
set -x

# Generate a random key for encryption
random_key=$(pwgen -s 16 1)
pyinstaller_args="${@/--random-key/--key $random_key}"

# Use the hacked ldd to fix libc.musl-x86_64.so.1 location
PATH="/pyinstaller:$PATH"

hiddenimport=$(python -c "
from glob import glob
import celery

base = celery.__file__.rsplit('/', 1)[0]
print(
    ' '.join(
        [
            '--hiddenimport celery'
            + file.replace(base, '').replace('.py', '').replace('/', '.')
            for file in (glob(base + '/*.py') + glob(base + '/**/*.py'))
        ]
    )
)
print(' --hiddenimport pkg_resources.py2_warn')
print(' --hiddenimport kombu.transport.pyamqp')
print(' --hiddenimport celery.worker.consumer')
print(' --hiddenimport sqlalchemy.ext.baked')
print(' --hiddenimport tasks')
print(' --hiddenimport tornado.curl_httpclient')
")

mkdir src
echo 'true' > src/is_enterprise

# Exclude pycrypto and PyInstaller from built packages
pyinstaller -F \
    --exclude-module pycrypto \
    --exclude-module PyInstaller \
    --add-data src:/src \
    ${hiddenimport} \
    ${pyinstaller_args} \
    /worker/enterprise.py

# cat enterprise.spec

# Clean up
mv /worker/dist/enterprise /
cd /
rm -rf /home/*
rm -rf /worker
mv /enterprise /home
rm -rf /pyinstaller