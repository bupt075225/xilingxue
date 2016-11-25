#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys

from models import User
from transwarp import db

u = User(name='test', email='test@example.com', password='123456', image='about:blank')
u.insert()

print "new user id:", u.id

count = u.count_all()
print "query count:", count

countBy = u.count_by("test@example.com")
print "query count by email:", countBy

#while count > 0:
u1 = User.find_first('where email=?', 'test@example.com')
print 'find user\'s name:', u1.name
u1.delete()
    #count -= 1

u2 = User.find_first('where email=?', 'test@example.com')
print 'find user:', u2
