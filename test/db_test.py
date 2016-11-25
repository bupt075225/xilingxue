#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest
from transwarp import db

class TestDb(unittest.TestCase):
	def setUp(self):
		print 'Create DB engine...'

	def tearDown(self):
		print 'tear down...'

	def test_createTable(self):
		print 'Create table testcase'
		result = update('create table user (id int primary key, name text, email text, passwd text, last_modified real)')
		self.assertEquals(result, 0)

#if __name__ == '__main__':
	#unittest.main()
