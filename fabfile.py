#!/usr/bin/env python
# -*- coding:utf-8 -*-

'''
Deployment toolkit
'''

import os,re
from datetime import datetime
from fabric.api import *

env.user = 'admin'
env.sudo_user = 'root'
env.hosts = ['10.104.128.190']

db_user = 'root'
db_password = 'Passwd1#'

_TAR_FILE = 'dist-xilingxue.tar.gz'
_REMOTE_TMP_TAR = '/tmp/%s' % _TAR_FILE
_REMOTE_BASE_DIR = '/srv/xilingxue/'

def _current_path():
    return os.path.abspath('.')

def _now():
    return datetime.now().strftime('%y-%m-%d_%H.%M.%S')

def build():
    '''
    Build distribute package.
    '''
    includes = ['static', 'templates', 'transwarp', '*.py']
    excludes = ['test', '.*', '*.pyc', '*.pyo']
    local('rm -f dist/%s' % _TAR_FILE)
    with lcd(os.path.join(_current_path(), 'www')):
        cmd = ['tar', '--dereference', '-czvf', '../dist/%s' % _TAR_FILE]
        cmd.extend(['--exclude=\'%s\'' % ex for ex in excludes])
        cmd.extend(includes)
        local(' '.join(cmd))

def deploy():
    newdir = 'www-%s' % _now()
    # 删除已有的tar文件
    run('rm -f %s' % _REMOTE_TMP_TAR)
    # 上传新的tar文件
    put('dist/%s' % _TAR_FILE, _REMOTE_TMP_TAR)
    # 创建新目录
    with cd(_REMOTE_BASE_DIR):
        sudo('mkdir %s' % newdir)
    # 解压到新目录
    with cd('%s%s' % (_REMOTE_BASE_DIR, newdir)):
        sudo('tar -xzvf %s' % _REMOTE_TMP_TAR)
    # 重置软链接
    with cd(_REMOTE_BASE_DIR):
        sudo('rm -f www')
        sudo('ln -s %s www' % newdir)
        sudo('chown root:root www')
        sudo('chown -R root:root %s' % newdir)
    # 重启Python服务和nginx服务器
    with settings(warn_only=True):
        sudo('supervisorctl stop xilingxue')
        sudo('supervisorctl start xilingxue')
        sudo('service nginx restart')

RE_FILES = re.compile('\r?\n')

def rollback():
    '''
    回滚到旧版本
    '''
    with cd(_REMOTE_BASE_DIR):
        r = run('ls -p -')
        files = [s[:-1] for s in RE_FILES.split(r) if s.startswith('www-') and s.endswith('/')]
        files.sort(cmp=lambda s1, s2: 1 if s1 < s2 else -1)
        r = run('ls -l www')
        ss = r.split(' -> ')
        if len(ss) != 2:
            print ('ERROR: \'www\' is not a symbol link.')
            return
        current = ss[1]
        print ('Found current symbol link points to: %s\n' % current)
        try:
            index = files.index(current)
        except ValueError, e:
            print ('ERROR: symbol link is invalid.')
            return
        if len(files) == index + 1:
            print ('ERROR:already the oldest version')
        old = files[index + 1]
        print ('==============================================')
        for f in files:
            if f == current:
                print ('    Current ---> %s' % current)
            elif f == old:
                print ('Rollback to ---> %s' % old)
            else:
                print ('                 %s' % f)
        print ('==============================================')
        print ('')
        yn = raw_input ('continue? y/N ')
        if yn != 'y' and yn != 'Y':
            print ('Rollback cancelled.')
            return
        print ('Start rollback...')
        sudo('rm -f www')
        sudo('ln -s %s www' % old)
        sudo('chown www-data:www-data www')
        with settings(warn_only=True):
            sudo('supervisorctl stop xilingxue')
            sudo('supervisorctl start xilingxue')
            sudo('/etc/init.d/nginx reload')
        print ('ROLLBACKED OK')

