# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function
from django.core.management.base import BaseCommand, CommandError
from django.utils import translation
from django.conf import settings

from data_migration.migration import Importer, Migrator

import sys

class Command(BaseCommand):
    help = 'Migrates old data into the new django schema'
    can_import_settings = True

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Commits the Changes to DB if all migrations are done right.',
            dest='commit_changes',
            default=False
        )
        parser.add_argument(
            '--exclude',
            action='append',
            metavar='APP',
            help='Excludes the supplied app from beeing migrated.',
            dest='excluded_apps',
            default = []
        )
        parser.add_argument(
            '--include',
            action='append',
            metavar='APP',
            help='Includes the supplied app in the migrations.',
            dest='included_apps',
            default = []
        )
        parser.add_argument(
            '--logquery',
            action='store_true',
            help='Print the corresponding Query for each migration.',
            dest='logquery',
            default=False
        )

    def handle(self, *args, **options):
        translation.activate(settings.LANGUAGE_CODE)

        excluded_apps = options.get('excluded_apps', [])
        included_apps = options.get('included_apps', [])

        sys.stdout.write("Importing migrations ...\n")
        Importer.import_all(excludes=excluded_apps, includes=included_apps)

        sys.stdout.write("Running migrations ...\n")
        Migrator.migrate(
            commit=options.get('commit_changes', False),
            log_queries=options.get('logquery', False)
        )

        sys.stdout.write("Done\n")
