import pgtrigger


def lessonmedia_unifier(lessonmedia_table: str, lesson_table: str):
    return pgtrigger.Trigger(
        name=f"{lessonmedia_table}_unifier",
        operation=pgtrigger.Insert | pgtrigger.Update,
        when=pgtrigger.Before,
        func=f"""
            IF EXISTS (
                SELECT 1
                FROM {lessonmedia_table} lm
                JOIN {lesson_table} l ON l.id = lm.lesson_id
                WHERE lm.media_id = NEW.media_id
                  AND l.course_id = (
                      SELECT course_id
                      FROM {lesson_table}
                      WHERE id = NEW.lesson_id
                      LIMIT 1
                  )
                  AND lm.id IS DISTINCT FROM NEW.id
            ) THEN
                RAISE EXCEPTION 'Media already exists in this course';
            END IF;
            RETURN NEW;
        """,
    )


def course_create_grading_policy(course_table: str, gradingpolicy_table: str):
    return pgtrigger.Trigger(
        name=f"{course_table}_create_grading_policy",
        operation=pgtrigger.Insert,
        when=pgtrigger.After,
        func=f"""
            INSERT INTO {gradingpolicy_table} (
                course_id, assessment_weight, completion_weight, completion_passing_point
            ) VALUES (
                NEW.id, 100, 0, 80
            );
            RETURN NEW;
        """,
    )
