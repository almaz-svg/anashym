from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse


def live(request):
    return JsonResponse({'status':'live'})


def ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            return JsonResponse({'status':'not_ready','reason':'migrations_pending'},status=503)
    except Exception:
        return JsonResponse({'status':'not_ready','reason':'database_unavailable'},status=503)
    return JsonResponse({'status':'ready'})
