import time

from django.apps import apps
from django.conf import settings
from django.db import connection, models
from django.utils.translation import gettext_lazy as _
from pghistory import utils


class SyncRecord(models.Model):
    synced = models.DateTimeField(_("Sync Date"), auto_now_add=True, db_index=True)
    count = models.IntegerField(_("Sync Count"), db_index=True)
    duration = models.FloatField(_("Duration (seconds)"), db_index=True)

    class Meta:
        verbose_name = _("Sync Record")
        verbose_name_plural = _("Sync Records")


class HotEvent(models.Model):
    pgh_slug = models.TextField(_("Slug"), unique=True)
    pgh_model = models.CharField(_("Event Model"), max_length=64, db_index=True)
    pgh_id = models.BigIntegerField(_("Event ID"))
    pgh_created_at = models.DateTimeField(_("Created At"), db_index=True)
    pgh_label = models.TextField(_("Label"))
    pgh_data = utils.JSONField(_("Data"), null=True, blank=True)
    pgh_diff = utils.JSONField(_("Diff"), null=True, blank=True)
    pgh_context_id = models.UUIDField(_("Context ID"), null=True, blank=True)
    pgh_context = utils.JSONField(_("Context"), null=True, blank=True)
    pgh_obj_model = models.CharField(_("Data Model"), max_length=64, db_index=True)
    pgh_obj_id = models.TextField(_("Data ID"), null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = _("Hot Event")
        verbose_name_plural = _("Hot Events")
        indexes = [models.Index(fields=["pgh_obj_model", "pgh_obj_id", "pgh_created_at"])]

    @classmethod
    def get_event_models(cls):
        event_models = []
        for model in apps.get_models():
            if model == cls:
                continue
            if model._meta.app_label == "pghistory":
                continue
            if hasattr(model, "pgh_id") and hasattr(model, "pgh_created_at") and hasattr(model, "pgh_label"):
                event_models.append(model)
        return event_models

    @classmethod
    def sync(cls):
        start_time = time.time()

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT synced FROM tracking_syncrecord ORDER BY synced DESC LIMIT 1
            """)

            result = cursor.fetchone()
            last_sync = result[0] if result else None

            union_queries = []
            params = []

            for model_class in cls.get_event_models():
                model_label = f"{model_class._meta.app_label}.{model_class.__name__}"
                table_name = model_class._meta.db_table
                tracked_model = model_class.pgh_tracked_model._meta.label

                conditions = [f"pgh_created_at >= NOW() - INTERVAL '{settings.HOT_EVENTS_RETENTION_DAYS} days'"]
                if last_sync:
                    conditions.append("pgh_created_at > %s")
                    params.append(last_sync)

                where_clause = " AND ".join(conditions)

                union_queries.append(f"""
                    SELECT 
                        CONCAT('{model_label}', ':', pgh_id) as pgh_slug,
                        '{model_label}' as pgh_model,
                        pgh_id,
                        pgh_created_at,
                        pgh_label,
                        (row_to_json({table_name}.*)::jsonb - 'pgh_id' - 'pgh_created_at' - 'pgh_label' - 'pgh_context_id' - 'pgh_obj_id') as pgh_data,
                        NULL::jsonb as pgh_diff,
                        pgh_context_id,
                        NULL::jsonb as pgh_context,
                        '{tracked_model}' as pgh_obj_model,
                        pgh_obj_id::text as pgh_obj_id
                    FROM {table_name}
                    WHERE {where_clause}
                """)

            if not union_queries:
                return {"synced_count": 0, "duration": 0}

            full_query = f"""
                INSERT INTO tracking_hotevent (
                    pgh_slug, pgh_model, pgh_id, pgh_created_at, pgh_label,
                    pgh_data, pgh_diff, pgh_context_id, pgh_context,
                    pgh_obj_model, pgh_obj_id
                )
                WITH new_events AS ( {" UNION ALL ".join(union_queries)})
                SELECT * FROM new_events ON CONFLICT (pgh_slug) DO NOTHING
            """

            cursor.execute(full_query, params)
            synced_count = cursor.rowcount

            if synced_count > 0:
                cursor.execute("""
                    WITH target_events AS (
                        SELECT pgh_slug, pgh_obj_model, pgh_obj_id, pgh_created_at, pgh_data
                        FROM tracking_hotevent
                        WHERE pgh_diff IS NULL
                    ),
                    prev_events AS (
                        SELECT DISTINCT ON (t.pgh_slug)
                            t.pgh_slug,
                            p.pgh_data as prev_pgh_data
                        FROM target_events t
                        LEFT JOIN tracking_hotevent p
                            ON p.pgh_obj_model = t.pgh_obj_model
                            AND p.pgh_obj_id = t.pgh_obj_id
                            AND p.pgh_created_at < t.pgh_created_at
                        ORDER BY t.pgh_slug, p.pgh_created_at DESC
                    )
                    UPDATE tracking_hotevent
                    SET pgh_diff = (
                        SELECT JSONB_OBJECT_AGG(curr_data.key, array[prev_data.value, curr_data.value])
                        FROM JSONB_EACH(tracking_hotevent.pgh_data) curr_data
                        LEFT JOIN JSONB_EACH(prev_events.prev_pgh_data) prev_data 
                            ON curr_data.key = prev_data.key
                        WHERE curr_data.key NOT LIKE 'pgh_%%'
                          AND curr_data.key NOT IN ('created', 'modified', 'deleted')
                          AND prev_data.value IS DISTINCT FROM curr_data.value
                          AND prev_data.value IS NOT NULL
                    )
                    FROM prev_events
                    WHERE tracking_hotevent.pgh_slug = prev_events.pgh_slug
                """)

                cursor.execute("""
                    UPDATE tracking_hotevent
                    SET pgh_context = pc.metadata
                    FROM pghistory_context pc
                    WHERE tracking_hotevent.pgh_context_id = pc.id
                      AND tracking_hotevent.pgh_context IS NULL
                """)

            duration = time.time() - start_time
            SyncRecord.objects.create(count=synced_count, duration=duration)

            return {"synced_count": synced_count, "duration": duration}

    @classmethod
    def cleanup(cls):
        start_time = time.time()

        with connection.cursor() as cursor:
            cursor.execute(f"""
                DELETE FROM tracking_hotevent 
                WHERE pgh_created_at <= NOW() - INTERVAL '{settings.HOT_EVENTS_RETENTION_DAYS} days'
            """)

            deleted_count = cursor.rowcount
            duration = time.time() - start_time

            return {"deleted_count": deleted_count, "duration": duration}
