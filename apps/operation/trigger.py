import pgtrigger


def thread_comment_stats(thread_table: str, comment_table: str):
    return [
        pgtrigger.Trigger(
            name=f"{comment_table}_insert",
            when=pgtrigger.After,
            operation=pgtrigger.Insert,
            func=f"""
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM {thread_table} WHERE id = NEW.thread_id) THEN
                        RAISE EXCEPTION 'Thread ID % does not exist', NEW.thread_id;
                    END IF;

                    WITH stats AS (
                        SELECT
                            COUNT(*) FILTER (WHERE rating IS NOT NULL AND rating > 0) AS rating_count,
                            COALESCE(SUM(rating) FILTER (WHERE rating IS NOT NULL AND rating > 0), 0) AS rating_sum
                        FROM {comment_table}
                        WHERE thread_id = NEW.thread_id AND deleted = false AND id != NEW.id
                    )
                    UPDATE {thread_table}
                    SET 
                        comment_count = comment_count + (NOT NEW.deleted)::int,
                        rating_count = (SELECT rating_count FROM stats) + 
                                       (NEW.rating IS NOT NULL AND NEW.rating > 0)::int,
                        rating_sum = (SELECT rating_sum FROM stats) + 
                                     COALESCE(NULLIF(NEW.rating, 0), 0),
                        rating_avg = CASE
                            WHEN (SELECT rating_count FROM stats) + (NEW.rating IS NOT NULL AND NEW.rating > 0)::int > 0 THEN
                                ((SELECT rating_sum FROM stats) + COALESCE(NULLIF(NEW.rating, 0), 0))::numeric / 
                                ((SELECT rating_count FROM stats) + (NEW.rating IS NOT NULL AND NEW.rating > 0)::int)
                            ELSE 0
                        END
                    WHERE id = NEW.thread_id;

                    RETURN NEW;
                END;
            """,
        ),
        pgtrigger.Trigger(
            name=f"{comment_table}_delete",
            when=pgtrigger.After,
            operation=pgtrigger.Delete,
            func=f"""
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM {thread_table} WHERE id = OLD.thread_id) THEN
                        RAISE EXCEPTION 'Thread ID % does not exist', OLD.thread_id;
                    END IF;

                    WITH stats AS (
                        SELECT
                            COUNT(*) AS remaining_count,
                            COUNT(*) FILTER (WHERE rating IS NOT NULL AND rating > 0) AS rating_count,
                            COALESCE(SUM(rating) FILTER (WHERE rating IS NOT NULL AND rating > 0), 0) AS rating_sum
                        FROM {comment_table}
                        WHERE thread_id = OLD.thread_id AND id != OLD.id AND deleted = false
                    )
                    UPDATE {thread_table}
                    SET 
                        comment_count = (SELECT remaining_count FROM stats),
                        rating_count = (SELECT rating_count FROM stats),
                        rating_sum = (SELECT rating_sum FROM stats),
                        rating_avg = CASE
                            WHEN (SELECT rating_count FROM stats) > 0 THEN
                                (SELECT rating_sum FROM stats)::numeric / (SELECT rating_count FROM stats)
                            ELSE 0
                        END
                    WHERE id = OLD.thread_id;

                    RETURN OLD;
                END;
            """,
        ),
        pgtrigger.Trigger(
            name=f"{comment_table}_update",
            when=pgtrigger.After,
            operation=pgtrigger.Update,
            func=f"""
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM {thread_table} WHERE id = NEW.thread_id) THEN
                        RAISE EXCEPTION 'Thread ID % does not exist', NEW.thread_id;
                    END IF;

                    IF NEW.thread_id != OLD.thread_id THEN
                        RAISE EXCEPTION 'Cannot change thread_id of a comment';
                    END IF;

                    WITH stats AS (
                        SELECT
                            COUNT(*) FILTER (WHERE id != OLD.id AND NOT deleted) + 
                                (NOT NEW.deleted)::int AS total_count,
                            COUNT(*) FILTER (WHERE id != OLD.id AND rating IS NOT NULL AND rating > 0 AND NOT deleted) + 
                                (NEW.rating IS NOT NULL AND NEW.rating > 0 AND NOT NEW.deleted)::int AS rating_count,
                            COALESCE(SUM(rating) FILTER (WHERE id != OLD.id AND rating IS NOT NULL AND rating > 0 AND NOT deleted), 0) + 
                                CASE WHEN NEW.rating IS NOT NULL AND NEW.rating > 0 AND NOT NEW.deleted THEN NEW.rating ELSE 0 END AS rating_sum
                        FROM {comment_table}
                        WHERE thread_id = NEW.thread_id
                    )
                    UPDATE {thread_table}
                    SET 
                        comment_count = (SELECT total_count FROM stats),
                        rating_count = (SELECT rating_count FROM stats),
                        rating_sum = (SELECT rating_sum FROM stats),
                        rating_avg = CASE
                            WHEN (SELECT rating_count FROM stats) > 0 THEN
                                (SELECT rating_sum FROM stats)::numeric / (SELECT rating_count FROM stats)
                            ELSE 0
                        END
                    WHERE id = NEW.thread_id;

                    RETURN NEW;
                END;
            """,
        ),
    ]
