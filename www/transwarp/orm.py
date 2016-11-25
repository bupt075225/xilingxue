#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
数据库对象-关系映射(ORM,Object Relational Mapping)模块
将一个类对应一个表，关系数据库的一行映射为一个对象
"""

import time
import logging
import db

"""
保存数据库表的字段名和字段类型
"""
class Field(object):
    _count = 0
    def __init__(self, **kv):
        self.name = kv.get('name', None)
        self._default = kv.get('default', None)
        self.primary_key = kv.get('primary_key', False)
        self.nullable = kv.get('nullable', False)
        self.updatable = kv.get('updatable', True)
        self.insertable = kv.get('insertable', True)
        self.ddl = kv.get('ddl', '')
        self._order = Field._count
        Field._count = Field._count + 1

    @property
    def default(self):
        d = self._default
        return d() if callable(d) else d

    def __str__(self):
        s = ['<%s:%s,%s,default(%s),' % (self.__class__.__name__, self.name, self.ddl, self._default)]
        self.nullable and s.append('N')
        self.updatable and s.append('U')
        self.insertable and s.append('I')
        s.append('>')
        return ''.join(s)

"""
定义各种类型的Field
"""
class StringField(Field):
    def __init__(self, **kv):
        if not 'default' in kv:
            kv['default'] = ''
        if not 'ddl' in kv:
            kv['ddl'] = 'varchar(255)'
        super(StringField, self).__init__(**kv)

class IntegerField(Field):
    def __init__(self, **kv):
        if not 'default' in kv:
            kv['default'] = 0
        if not 'ddl' in kv:
            kv['ddl'] = 'bigint'

        super(IntegerField, self).__init__(**kv)

class FloatField(Field):
    def __init__(self, **kv):
        if not 'default' in kv:
            kv['default'] = 0.0
        if not 'ddl' in kv:
            kv['ddl'] = 'real'

        super(FloatField, self).__init__(**kv)

class BooleanField(Field):
    def __init__(self, **kv):
        if not 'default' in kv:
            kv['default'] = False
        if not 'ddl' in kv:
            kv['ddl'] = 'bool'

        super(BooleanField, self).__init__(**kv)

class TextField(Field):
    def __init__(self, **kv):
        if not 'default' in kv:
            kv['default'] = ''
        if not 'ddl' in kv:
            kv['ddl'] = 'text'

        super(TextField, self).__init__(**kv)

class BlobField(Field):
    def __init__(self, **kv):
        if not 'default' in kv:
            kv['default'] = ''
        if not 'ddl' in kv:
            kv['ddl'] = 'blob'

        super(BlobField, self).__init__(**kv)

class VersionField(Field):
    def __init__(self, name=None):
        super(VersionField, self).__init__(name=name, default=0, ddl='biginit')

_triggers = frozenset(['pre_insert', 'pre_update', 'pre_delete'])


def _gen_sql(table_name, mappings):
    pk = None
    sql = ['-- generating SQL for %s:' % table_name, 'create table `%s` (' % table_name]
    for f in sorted(mappings.values(), lambda x, y: cmp(x._order, y._order)):
        if not hasattr(f, 'ddl'):
            raise StandardError('no ddl in field "%s".' % n)
        ddl = f.ddl
        nullable = f.nullable
        if f.primary_key:
            pk = f.name
        sql.append(nullable and '`%s` %s,' % (f.name, ddl) or ' `%s` %s not null,' % (f.name, ddl))

    sql.append(' primary key(`%s`)' % pk)
    sql.append(');')
    return '\n'.join(sql)

"""
动态定制继承自Model的子类，自动通过ModelMetaclass扫描映射关系，并
存储到自身的class中
元类可以隐式地继承到子类，但子类自己却感觉不到
"""
class ModelMetaclass(type):
    #__new__方法接收到的参数依次是：当前准备创建的对象，类名，父类集合，类方法集合
    def __new__(cls, name, bases, attrs):
        # 排除掉对Model类的修改
        if name=='Model':
            return type.__new__(cls, name, bases, attrs)

        # 保存子类信息
        if not hasattr(cls, 'subclasses'):
            cls.subclasses = {}
        if not name in cls.subclasses:
            cls.subclasses[name] = name
        else:
            logging.warning("Redefine class: %s" % name)

        logging.info("Scan ORMapping %s..." % name)
        # 在子类中查找定义的类属性，找到Field属性就保存到mappings中
        mappings = dict() #读取cls的Field
        primary_key = None # 查找primary key字段
        for k, v in attrs.iteritems():
            if isinstance(v, Field):
                if not v.name:
                    v.name = k
                logging.info("Found mapping:%s==>%s" % (k,v))
                # 检查重复定义的主键
                if v.primary_key:
                    if primary_key:
                        raise TypeError("Cannot define more than 1 primary key in class:%s" % name)
                    if v.updatable:
                        logging.warning("NOTE:change primary key to non-updatable")
                        v.updatable = False
                    if v.nullable:
                        logging.warning("NOTE:change primary key to non-nullable")
                        v.nullable = False
                    primary_key = v
                mappings[k] = v
        # 检查是否存在主键
        if not primary_key:
            raise TypeError("Primary key not defined in class: %s" % name)
        # 从子类属性中删除上面找到的Field属性
        for k in mappings.iterkeys():
            attrs.pop(k)

        # 给cls增加一些字段
        if not '__table__' in attrs:
            attrs['__table__'] = name.lower()

        attrs['__mappings__'] = mappings
        attrs['__primary_key__'] = primary_key
        attrs['__sql__'] = lambda self: _gen_sql(attrs['__table__'], mappings)

        for trigger in _triggers:
            if not trigger in attrs:
                attrs[trigger] = None

        return type.__new__(cls, name, bases, attrs)


"""
ORM映射的基类
"""
class Model(dict):
    # 使用元类ModelMetaclass来动态定制类
    __metaclass__=ModelMetaclass

    def __init__(self, **kv):
        super(Model, self).__init__(**kv)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    # 添加class方法
    @classmethod
    def get(cls, pk):
        """
        通过主键查询
        """
        d = db.select_one('select * from %s where %s=?' % (cls.__table__, cls.__primary_key__.name), pk)
        return cls(**d) if d else None

    @classmethod
    def find_first(cls, where, *args):
        """
        条件查询，返回一个查询结果，如果查询到多个结果，也只返回第一个。
        如果没有查询到结果返回None
        """
        d = db.select_one('select * from %s %s' % (cls.__table__, where), *args)
        return cls(**d) if d else None

    @classmethod
    def find_all(cls, *args):
        """
        查询所有，返回一个列表
        """
        L = db.select('select * from `%s`' % cls.__table__)
        return [cls(**d) for d in L]

    @classmethod
    def find_by(cls, where, *args):
        """
        条件查询，返回一个列表包含所有查询结果
        """
        L = db.select('select * from `%s` `%s`' % (cls.__table__, where), *args)
        return [cls(**d) for d in L]

    @classmethod
    def count_all(cls):
        return db.select_int('select count(`%s`) from `%s`' % (cls.__primary_key__.name, cls.__table__))

    @classmethod
    def count_by(cls, where, *args):
        return db.select_int('select count(`%s`) from `%s` `%s`' % (cls.__primary_key__.name, cls.__table__, where), *args)


    # 添加实例方法
    def update(self):
        self.pre_update and self.pre_update()
        L = []
        args = []
        for k,v in self.__mappings__.iteritems():
            if v.updatable:
                if hasattr(self, k):
                    arg = getattr(self, k)
                else:
                    arg = v.default
                    setattr(self, k, arg)
                L.append('`%s`=?' % k)
                args.append(arg)
        pk = self.__primary_key__.name
        args.append(getattr(self, pk))
        db.update('update `%s` set % where %s=?' % (self.__table__, ','.join(L), pk), *args)
        return self

    def delete(self):
        self.pre_delete and self.pre_delete()
        pk = self.__primary_key__.name
        args = (getattr(self, pk), )
        db.update('delete from `%s` where `%s`=?' % (self.__table__, pk), *args)
        return self

    def insert(self):
        self.pre_insert and self.pre_insert()
        params = {}
        for k, v in self.__mappings__.iteritems():
            if v.insertable:
                if not hasattr(self, k):
                    setattr(self, k, v.default)
                params[v.name] = getattr(self, k)
        db.insert('%s' % self.__table__, **params)
        return self
        db.insert(self.__table__, **params)
        return self

if __name__=='__main__':
    logging.basicConfig(level=logging.DEBUG)
    #db.update('drop table if exists user')
    #db.update('create table user (id int primary key, name text, email text, passwd text, last_modified real)')
