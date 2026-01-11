from typing import TYPE_CHECKING
from uuid import uuid4

import mimesis
from django.conf import settings
from django.db.models import QuerySet
from factory.declarations import Iterator, LazyFunction, SubFactory
from factory.django import DjangoModelFactory
from factory.helpers import post_generation
from mimesis.plugins.factory import FactoryField

from apps.assignment.models import Assignment
from apps.common.factory import LearningObjectFactory
from apps.competency.models import Certificate
from apps.content.models import Media
from apps.content.tests.factories import MediaFactory
from apps.course.models import (
    TEMPLATE_SCHEDULES,
    Assessment,
    Course,
    CourseInstructor,
    CourseSurvey,
    Lesson,
    LessonMedia,
    MessagePreset,
)
from apps.discussion.models import Discussion
from apps.exam.models import Exam
from apps.operation.models import Category
from apps.operation.tests.factories import FAQFactory, HonorCodeFactory, InstructorFactory
from apps.survey.models import Survey

generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)


class MessagePresetFactory(DjangoModelFactory[MessagePreset]):
    title = FactoryField("text.title")
    description = FactoryField("text")
    templates = LazyFunction(lambda: list(TEMPLATE_SCHEDULES.keys()))

    class Meta:
        model = MessagePreset
        django_get_or_create = ("title",)
        skip_postgeneration_save = True


class CourseFactory(LearningObjectFactory[Course]):
    passing_point = FactoryField("choice", items=[60, 80])
    max_attempts = FactoryField("choice", items=[1, 2])
    verification_required = True

    owner = SubFactory("account.tests.factories.UserFactory")
    objective = FactoryField("text")
    preview_url = None
    effort_hours = FactoryField("choice", items=[8, 16, 32])
    level = Iterator(Course.LevelChoices)
    honor_code = SubFactory(HonorCodeFactory)
    faq = SubFactory(FAQFactory)
    message_preset = SubFactory(MessagePresetFactory)

    class Meta:
        model = Course
        django_get_or_create = ("title", "owner")
        skip_postgeneration_save = True

    if TYPE_CHECKING:
        categories: QuerySet[Category]
        related_courses: QuerySet[Course]
        certificates: QuerySet[Certificate]
        lesson_set: QuerySet[Lesson]
        pk: int

    @post_generation
    def post_generation(self, create, extracted, **kwargs):
        if not create:
            return

        # manytomany
        self.categories.set(Category.objects.filter(depth=3).order_by("?")[: generic.random.randint(1, 2)])
        self.related_courses.set(Course.objects.exclude(id=self.pk).order_by("?")[: generic.random.randint(1, 2)])
        self.certificates.set(Certificate.objects.order_by("?")[: generic.random.randint(1, 2)])

        # instructor
        instructors = InstructorFactory.create_batch(generic.random.randint(1, 3))
        if instructors:
            CourseInstructor.objects.bulk_create(
                [
                    CourseInstructor(course=self, instructor=instructor, lead=True if i == 0 else False)
                    for i, instructor in enumerate(instructors)
                ],
                ignore_conflicts=True,
            )

        # survey
        surveys = Survey.objects.order_by("?")[: generic.random.randint(1, 2)]
        if surveys:
            CourseSurvey.objects.bulk_create(
                [
                    CourseSurvey(
                        course=self,
                        survey=survey,
                        timing=generic.random.choice(CourseSurvey.TimingChoices.choices)[0],
                        ordering=i,
                    )
                    for i, survey in enumerate(surveys)
                ],
                ignore_conflicts=True,
            )

        # lesson
        medias = Media.objects.order_by("?")[: generic.random.choice([8, 16, 32])]

        for i, media in enumerate(medias):
            lesson, created = Lesson.objects.get_or_create(
                course=self,
                title=media.title,
                defaults={"description": media.description, "start_offset": i * 7, "end_offset": 7, "ordering": i},
            )

            if created:
                LessonMedia(lesson=lesson, media=media, ordering=0).save()

                if i in [2, 4]:
                    media = MediaFactory.create(owner=self.owner, url=f"{generic.internet.url()}/{uuid4().hex}.mp4")
                    LessonMedia(lesson=lesson, media=media, ordering=i).save()

        # assessment
        discussions = Discussion.objects.order_by("?")[: generic.random.randint(1, 2)]
        exams = Exam.objects.order_by("?")[: generic.random.randint(1, 2)]
        assignments = Assignment.objects.order_by("?")[: generic.random.randint(1, 2)]

        last_lesson = self.lesson_set.last()
        course_days = last_lesson.start_offset + 7 if last_lesson else 30

        weeks = course_days // 7
        assessments_to_create = []

        discussion_weeks = [1, 5][: len(discussions)] if weeks >= 5 else [1][: len(discussions)]
        assignment_weeks = [2, 6][: len(assignments)] if weeks >= 6 else [2][: len(assignments)]

        if weeks >= 8:
            exam_weeks = [weeks // 2, weeks][: len(exams)]
        elif weeks >= 4:
            exam_weeks = [weeks][: len(exams)]
        else:
            exam_weeks = []

        for i, discussion in enumerate(discussions):
            if i < len(discussion_weeks):
                week = discussion_weeks[i]
                if week <= weeks:
                    start_offset = (week - 1) * 7
                    assessments_to_create.append(
                        Assessment(course=self, weight=20, start_offset=start_offset, end_offset=7, item=discussion)
                    )

        for i, assignment in enumerate(assignments):
            if i < len(assignment_weeks):
                week = assignment_weeks[i]
                if week <= weeks:
                    start_offset = (week - 1) * 7
                    assessments_to_create.append(
                        Assessment(course=self, weight=30, start_offset=start_offset, end_offset=7, item=assignment)
                    )

        for i, exam in enumerate(exams):
            if i < len(exam_weeks):
                week = exam_weeks[i]
                start_day = (week - 1) * 7
                assessments_to_create.append(
                    Assessment(course=self, weight=50, start_offset=start_day, end_offset=7, item=exam)
                )

        Assessment.objects.bulk_create(assessments_to_create, ignore_conflicts=True)
