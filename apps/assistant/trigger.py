import pgtrigger


def chat_ensure_single_active(chat_table: str):
    return pgtrigger.Trigger(
        name=f"{chat_table}_ensure_single_active",
        when=pgtrigger.Before,
        operation=pgtrigger.Insert | pgtrigger.Update,
        func=f"""
            BEGIN
                IF NEW.active = TRUE AND NEW.deleted IS NULL THEN
                    UPDATE {chat_table}
                    SET active = FALSE
                    WHERE user_id = NEW.user_id AND id != NEW.id AND active = TRUE AND deleted IS NULL;
                END IF;
                RETURN NEW;
            END;
        """,
    )


def chat_sync_message_count(chat_table: str, chat_message_table: str):
    return [
        pgtrigger.Trigger(
            name=f"{chat_message_table}_insert_message_count",
            when=pgtrigger.After,
            operation=pgtrigger.Insert,
            func=f"""
                BEGIN
                    IF NEW.deleted IS NULL THEN
                        UPDATE {chat_table}
                        SET message_count = message_count + 1,
                            last_message = NEW.created
                        WHERE id = NEW.chat_id;
                    END IF;
                    RETURN NEW;
                END;
            """,
        ),
        pgtrigger.Trigger(
            name=f"{chat_message_table}_update_message_count",
            when=pgtrigger.After,
            operation=pgtrigger.Update,
            func=f"""
                BEGIN
                    IF NEW.chat_id != OLD.chat_id THEN
                        RAISE EXCEPTION 'Cannot change chat_id of a message';
                    END IF;

                    IF OLD.deleted IS NULL AND NEW.deleted IS NOT NULL THEN
                        UPDATE {chat_table}
                        SET message_count = GREATEST(message_count - 1, 0),
                            last_message = (
                                SELECT MAX(created)
                                FROM {chat_message_table}
                                WHERE chat_id = NEW.chat_id AND deleted IS NULL
                            )
                        WHERE id = NEW.chat_id;
                    END IF;

                    IF OLD.deleted IS NOT NULL AND NEW.deleted IS NULL THEN
                        UPDATE {chat_table}
                        SET message_count = message_count + 1,
                            last_message = GREATEST(COALESCE(last_message, NEW.created), NEW.created)
                        WHERE id = NEW.chat_id;
                    END IF;

                    RETURN NEW;
                END;
            """,
        ),
    ]
