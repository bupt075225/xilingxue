#/usr/bin/env python
# -*- coding: utf-8 -*-

"""
数据库访问接口的python封装
"""
import sqlite3
import functools
import threading
import logging
import time
import uuid

class DBError(Exception):
    """
        数据异常类
    """
    pass

class MultiColumnsError(DBError):
    pass

class Dict(dict):
    """
    增强型字典，继承原有的字典，可以将两个列表打包成字典，实现dict(zip(list1, list2))
    """
    def __init__(self, names=(), values=(), **kwargs):
        super(Dict, self).__init__(**kwargs)
        self.update(dict(zip(names, values)))

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

def next_id(t=None):
    if t is None:
        t = time.time()
    return '%015d%s000' % (int(t * 1000), uuid.uuid4().hex)

def _profiling(start, sql=''):
    t = time.time() - start
    if t > 0.1:
        logging.warning('[PROFILING] [DB] %s: %s' % (t, sql))
    else:
        logging.info('[PROFILING] [DB] %s: %s' % (t, sql))


#数据库引擎对象
class _Engine(object):
    def __init__(self, connect):
        self._connect = connect

    def connect(self):
        return self._connect

#全局数据库引擎
engine = None

def createEngine(user, password, database, host='127.0.0.1', port=3306, **kwargs):
    """
    创建数据库引擎，实现全局对象`engine`
    """
    import mysql.connector
    global engine
    if engine is not None:
        raise DBError("Engine is alreadyinitialized.")

    #连接参数
    params = dict(user=user, password=password, database=database, host=host, port=port)
    #默认连接参数
    defaults = dict(use_unicode=True, charset='utf-8', collation='utf8_general_ci', autocommit=False)
    for k, v in defaults.iteritems():
        params[k] = kwargs.pop(k, v)
    #通过函数参数更新连接参数
    params.update(kwargs)
    params['buffered'] = True
    #创建engine全局对象
    engine = _Engine(lambda: mysql.connector.connect(**params))
    logging.info("Init mysql engine <%s> ok." % hex(id(engine)))

class _LasyConnection(object):
    """
    获取数据库引擎连接资源句柄connection
    通过connection获取cursor
    操作commit, roolback
    关闭连接 cleanup
    """
    def __init__(self):
        self.connection = None
    def cursor(self):
        if self.connection is None:
            connection = engine.connect()
            print 'debug here>>>>>>>>>>>>>>'
            print type(connection)
            print connection
            #connection = sqlite3.connect("test.db")
            logging.info("open connection <%s>..." % hex(id(connection)))
            self.connection = connection
        return self.connection.cursor()

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def cleanup(self):
        if self.connection:
            connection = self.connection
            self.connection = None
            logging.info("close connection <%s>..." % hex(id(connection)))
            connection.close()


#持有数据库连接的上下文对象
class _DbCtx(threading.local):
    def __init__(self):
        self.connection = None
        self.transactions = 0

    def isInit(self):
        return not self.connection is None

    def init(self):
        self.connection = _LasyConnection()
        self.transactions = 0

    def cleanup(self):
        self.connection.cleanup()
        self.connection = None

    def cursor(self):
        return self.connection.cursor()

_db_ctx = _DbCtx()

class _ConnectionCtx(object):
    def __enter__(self):
        global _db_ctx

        self.shouldCleanup = False
        if not _db_ctx.isInit():
            _db_ctx.init()
            self.shuldCleanup = True

        return self

    def __exit__(self, exctype, excvalue, traceback):
        global _db_ctx

        if self.shouldCleanup:
            _db_ctx.cleanup()

def connection():
    """
    对'_ConnectionCtx'的封装，提供对外接口
    with connection():
        do_some_db_operation()
    """
    return _ConnectionCtx()

def with_connection(func):
    """
    获取数据库连接和关闭装饰器
    @with_connection
    def foo(*args, **kwargs):
        do_some_db_operation()
    """
    @functools.wraps(func)
    def _wrapper(*args, **kwargs):
        with _ConnectionCtx():
            return func(*args, **kwargs)

    return _wrapper


class _TransactionCtx(object):
    def __enter__(self):
        global _db_ctx
        self.shouldCloseConn = False
        if not _db_ctx.is_init():
            _db_ctx.init()
            self.shouldCloseConn = True

        _db_ctx.transactions += 1
        logging.info('begin transaction...' if _db_ctx.transactions==1 else 'join current transaction...')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _db_ctx
        _db_ctx.transactions -= 1
        try:
            if _db_ctx.transactions==0:
                if exc_type is None:
                    self.commit()
                else:
                    self.rollback()
        finally:
            if self.shouldCloseConn:
                _db_ctx.cleanup()

    def commit(self):
        global _db_ctx
        logging.info('commit transaction...')
        try:
            _db_ctx.connection.commit()
            logging.info('commit ok.')
        except:
            logging.warning('commit failed. try rollback...')
            _db_ctx.connection.rollback()
            logging.warning('rollback ok.')
            raise

    def rollback(self):
        global _db_ctx
        logging.warning('rollback transaction...')
        _db_ctx.connection.rollback()
        logging.info('rollback ok.')


def transaction():
    return _TransactionCtx()


def with_transaction(func):
    @functools.wraps(func)
    def _wrapper(*args, **kwargs):
        _start = time.time()
        with _TransactionCtx():
            return func(*args, **kwargs)
        _profiling(_start)
    return _wrapper


@with_connection
def _select(sql, first, *args):
    """
    查询函数
    """
    global _db_ctx
    cursor = None
    #sql = sql.replace('?', "%s")
    args_tuple = tuple(args)
    logging.info('SQL: %s, ARGS: %s' % (sql, args_tuple))

    try:
        #通过数据库上下文获取查询游标`cursor`
        cursor = _db_ctx.connection.cursor()
        #执行sql查询
        cursor.execute(sql, args_tuple)
        #处理查询结果，返回对象列表
        if cursor.description:
            names = [x[0] for x in cursor.description]
        if first:
            values = cursor.fetchone()
            if not values:
                return None
            return Dict(names, values)
        return [Dict(names, x) for x in cursor.fetchall()]
    finally:
        #关闭游标
        if cursor:
            cursor.close()

@with_connection
def _update(sql, *args):
    global _db_ctx
    cursor = None
    #sql = sql.replace('?', '%s')
    logging.info('SQL: %s, ARGS: %s' % (sql, args))
    try:
        cursor = _db_ctx.connection.cursor()
        cursor.execute(sql, args)
        r = cursor.rowcount
        if _db_ctx.transactions == 0:
            logging.info('auto commit')
            _db_ctx.connection.commit()
        return r
    finally:
        if cursor:
            cursor.close()

def update(sql, *args):
    return _update(sql, *args)

def insert(table, **kwargs):
    cols, args = zip(*kwargs.iteritems())
    sql = 'insert into `%s` (%s) values (%s)' % (table, ','.join(['`%s`' % col for col in cols]), ','.join(['?' for i in range(len(cols))]))
    return _update(sql, *args)

def delete(sql, *args):
    return _update(sql, *args)

def select_int(sql, *args):
    d = _select(sql, True, *args)
    if len(d) != 1:
        raise MultiColumnsError('Expect only one column.')
    return d.values()[0]

def select(sql, *args):
    return _select(sql, False, *args)

def select_one(sql, *args):
    return _select(sql, True, *args)


if __name__=='__main__':
    logging.basicConfig(level=logging.DEBUG)
    #update('create table users (id int primary key, name text, email text, passwd text, last_modified real)')
