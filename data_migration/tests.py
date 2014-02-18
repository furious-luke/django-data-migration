# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from future.builtins import str

from django.test import TestCase, TransactionTestCase
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings
from django.contrib.auth.models import User, Group

from mock import patch
from io import StringIO

from .models import AppliedMigration
from .migration import is_a, Migration, Importer, Migrator

"""
Utility stuff
"""
def install_apps(apps):

    apps = [ "data_migration.test_apps.%s" % app for app in apps ]

    def real_decorator(function):
        def wrapper(*args, **kwargs):
            with patch.object(Importer, 'installed_apps') as method:
                method.return_value = apps
                function(*args, **kwargs)

        return wrapper
    return real_decorator


"""
Test Cases
"""
class ImporterTest(TestCase):

    @install_apps(['valid_a', 'valid_b' 'missing_spec'])
    def test_import_existing_migrations_with_respect_to_excludes(self):
        old_count = len(Migration.__subclasses__())
        Importer.import_all(excludes=["valid_b"])
        new_count = len(Migration.__subclasses__())

        self.assertEqual(new_count - old_count, 1)


from .test_apps.blog.models import Author, Post, Comment
from .test_apps.blog.data_migration_spec import *

class MigratorTest(TransactionTestCase):

    @install_apps(['valid_a', 'blog'])
    def test_that_no_abstract_migration_will_be_sorted_in(self):
        Importer.import_all()

        _sorted = Migrator.sorted_migrations()
        self.assertFalse(BaseMigration in _sorted)


    @install_apps(['valid_a', 'blog'])
    def test_topological_sorting(self):
        Importer.import_all()

        _sorted = Migrator.sort_based_on_dependency(
                    [AuthorMigration, PostMigration, CommentMigration])
        self.assertEqual(_sorted[0].model, Author)
        self.assertEqual(_sorted[1].model, Comment)
        self.assertEqual(_sorted[2].model, Post)


    @patch.object(Migrator, 'sorted_migrations')
    @patch('sys.stderr', new_callable=StringIO)
    def test_transaction_handling(self, stderr, sorted_migrations):
        sorted_migrations.return_value = [ AuthorMigration ]

        AuthorMigration.migrate = classmethod(
            lambda cls: AppliedMigration.objects.create(classname="test"))

        Migrator.migrate(commit=False)
        self.assertEqual(AppliedMigration.objects.count(), 0)

        Migrator.migrate(commit=True)
        self.assertEqual(AppliedMigration.objects.count(), 1)


class IsATest(TestCase):

    def test_normal_description(self):
        self.assertEqual(is_a(User, 'username', fk=True), {
            'klass': User,
            'attr': 'username',
            'm2m': False,
            'delimiter': u';',
            'skip_missing': False,
            'o2o': False,
            'exclude': False,
            'fk': True,
        })

    def test_that_class_and_attr_has_to_be_present(self):
        with self.assertRaises(ImproperlyConfigured):
            is_a(fk=True)

    def test_that_class_has_to_be_a_model(self):
        with self.assertRaises(ImproperlyConfigured):
            is_a(str(User), 'username', fk=True)

    def test_multiple_type_definition(self):
        with self.assertRaises(ImproperlyConfigured):
            is_a(User, 'username', fk=True, m2m=True)

    def test_exclude_from_processing(self):
        self.assertEqual(is_a(exclude=True), {
            'klass': None,
            'attr': None,
            'm2m': False,
            'delimiter': u';',
            'skip_missing': False,
            'o2o': False,
            'exclude': True,
            'fk': False,
        })

from datetime import datetime
from django.core import management

import os
import sqlite3

class MigrationTest(TransactionTestCase):

    def setUp(self):
        super(TransactionTestCase, self).setUp()

        self.db_path = os.path.join(
                os.path.dirname(__file__), 'test_apps/blog/blog_fixture.db')

        if not os.path.isfile(self.db_path):
            fixture = os.path.join(os.path.dirname(self.db_path), "fixtures.sql")
            conn = sqlite3.connect(self.db_path)
            conn.cursor().executescript(open(fixture).read())
            conn.close()


    def tearDown(self):
        super(TransactionTestCase, self).tearDown()

        if os.path.isfile(self.db_path):
            os.unlink(self.db_path)


    @patch('sys.stdout', new_callable=StringIO)
    @patch.object(Migration, '__subclasses__')
    def test_description(self, subclasses, stdout):
        subclasses.return_value = [
            BaseMigration, AuthorMigration, PostMigration, CommentMigration
        ]

        Migrator.migrate(commit=True)

        self.assertEqual(Author.objects.count(), 10)
        self.assertEqual(Comment.objects.count(), 20)
        self.assertEqual(Post.objects.count(), 10)

        post9 = Post.objects.get(id=9)
        self.assertEqual(post9.comments.count(), 3)
        self.assertEqual(post9.title,
                "lacinia at, iaculis quis, pede. Praesent eu dui. Cum sociis")
        self.assertEqual(post9.posted, datetime(2014, 10, 13, 8, 36, 59))


    @patch.object(AuthorMigration, 'hook_update_existing')
    @patch.object(AuthorMigration, 'hook_after_all')
    @patch.object(AuthorMigration, 'hook_after_save')
    @patch.object(AuthorMigration, 'hook_before_transformation')
    @patch.object(AuthorMigration, 'hook_before_all')
    @patch.object(Migration, '__subclasses__')
    @patch('sys.stdout', new_callable=StringIO)
    def test_hook_calling(self, stdout, subclasses, bef_all, bef_trans,
                          aft_save, aft_all, exist):

        subclasses.return_value = [ AuthorMigration ]
        Migrator.migrate(commit=True)

        self.assertFalse(exist.called)

        methods = [ bef_all, bef_trans, aft_save, aft_all ]
        for method in methods:
            self.assertTrue(method.called)

        self.assertEqual(AppliedMigration.objects.count(), 1)


    @patch.object(AuthorMigration, 'hook_after_save')
    @patch.object(AuthorMigration, 'hook_update_existing')
    @patch.object(Migration, '__subclasses__')
    @patch('sys.stdout', new_callable=StringIO)
    def test_updatable_migrations(self, stdout, subclasses, exist, aft_save):
        subclasses.return_value = [ AuthorMigration ]

        Migrator.migrate(commit=True)
        Author.objects.get(id=10).delete()
        self.assertFalse(exist.called)
        self.assertEqual(Author.objects.count(), 9)

        Migrator.migrate(commit=True)
        self.assertTrue(exist.called)
        self.assertEqual(exist.call_count, 9)
        self.assertEqual(aft_save.call_count, 11)
        self.assertEqual(Author.objects.count(), 10)


    @patch.object(Migration, '__subclasses__')
    @patch('sys.stderr', new_callable=StringIO)
    @patch('sys.stdout', new_callable=StringIO)
    def test_calling_management_command(self, stdout, stderr, sub):
        sub.return_value = [ AuthorMigration ]

        management.call_command('migrate_legacy_data', commit_changes=True)

        val = stderr.getvalue()
        self.assertFalse("is deprecated in favour of" in val)
        self.assertFalse("Not commiting! No changes" in val)
        self.assertTrue("Migrating element" in stdout.getvalue())


    @patch.object(Migration, '__subclasses__')
    @patch('sys.stderr', new_callable=StringIO)
    @patch('sys.stdout', new_callable=StringIO)
    def test_calling_deprecated_management_command(self, stdout, stderr, sub):
        sub.return_value = [ AuthorMigration ]

        management.call_command('migrate_this_shit', commit_changes=True)

        val = stderr.getvalue()
        self.assertTrue("is deprecated in favour of" in val)
        self.assertFalse("Not commiting! No changes" in val)
        self.assertTrue("Migrating element" in stdout.getvalue())
