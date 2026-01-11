import pgtrigger


def enrollment_content_exists(enrollment_table: str, content_type_table: str):
    return pgtrigger.Trigger(
        name=f"{enrollment_table}_content_exists",
        operation=pgtrigger.Insert | pgtrigger.Update,
        when=pgtrigger.Before,
        func=f"""
            DECLARE
                table_name text;
                exists_check boolean;
            BEGIN
                SELECT app_label || '_' || model INTO table_name
                FROM {content_type_table}
                WHERE id = NEW.content_type_id;

                EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I WHERE id = $1)', table_name)
                INTO exists_check USING NEW.content_id;

                IF NOT exists_check THEN
                    RAISE EXCEPTION 'Content % does not exist in %', NEW.content_id, table_name;
                END IF;

                RETURN NEW;
            END;
        """,
    )
