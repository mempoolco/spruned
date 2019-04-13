import os


def get_version(sql):
    table_info = "PRAGMA table_info('migrations')"
    if not sql.execute(table_info).fetchall():
        return 0
    version_query = "SELECT version from migrations"
    version = sql.execute(version_query).fetchone()
    return version and version[0] or 0


def gather_migrations():
    current_path = os.path.realpath(__file__).rstrip('__init__.py')
    files = os.listdir(current_path)
    return {
        int(x.replace('migration_', '').replace('.py', '')): current_path + x
        for x in files if x.startswith('migration_')
    }


def apply_migration(sql, migration):
    from importlib.machinery import SourceFileLoader
    module = SourceFileLoader('migration_%s' % migration, migration).load_module()
    module.migrate(sql)


def run(sql):
    version = get_version(sql)
    migrations = gather_migrations()
    from spruned.application.logging_factory import Logger
    Logger.root.debug(
        'Database migrations. Current version: %s, migrations available: %s', version, max(migrations.keys())
    )
    missing_migrations = sorted([x for x in migrations.keys() if x > version])
    for migration in missing_migrations:
        apply_migration(sql, migrations[migration])
