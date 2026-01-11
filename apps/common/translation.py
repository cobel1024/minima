from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

# unfold
_("Add new item")
_("Type to search")
_("No results found")
_("This page yielded into no results. Create a new item or reset your filters.")
_("Date")
_("App label")
_("Dark")
_("Light")
_("System")
_("You have been successfully logged out from the administration")
_("Welcome back to")
_("Return to site")
_(
    "Raw passwords are not stored, so there is no way to see this "
    + "user’s password, but you can change the password using "
    + '<a href="{}" class="text-primary-600 dark:text-primary-500">this form</a>.'
)
_("Select action")
_("Select value")
_("Run")
_("True")
_("False")
_("Unknown")
_("previous")
_("next")
_("content")
_("Choose file to upload")
_("No recent searches")
_("Search apps and models...")
_("General")

# django-treebeard
_("Relative to")
_("Position")
_("First child of")
_("Before")
_("After")

# taggit
_("A comma-separated list of tags.")
pgettext_lazy("A tag name", "name")
pgettext_lazy("A tag slug", "slug")
_("tags")
_("Taggit")

# phonenumber_field
pgettext_lazy(
    "{example_number} is a national phone number.",
    "Enter a valid phone number (e.g. {example_number}) or a number with an international call prefix.",
)

# local
_("unit")
_("Subject")
_("Training")
_("Item")
_("Filters")
_("Apply Filters")
_("Insert")
_("Update")
_("Delete")


# django celery results
_("Parameters")
_("Result")
_("Celery Results")
_("Task ID")
_("Celery ID for the Task that was run")
_("Periodic Task Name")
_("Name of the Periodic Task which was run")
_("Task Name")
_("Name of the Task which was run")
_("Task Positional Arguments")
_("JSON representation of the positional arguments used with the task")
_("Task Named Arguments")
_("JSON representation of the named arguments used with the task")
_("Task State")
_("Current state of the task being run")
_("Worker")
_("Worker that executes the task")
_("Result Content Type")
_("Content type of the result data")
_("Result Encoding")
_("The encoding used to save the task result data")
_("Result Data")
_("The data returned by the task.  Use content_encoding and content_type fields to read.")
_("Created DateTime")
_("Datetime field when the task result was created in UTC")
_("Started DateTime")
_("Datetime field when the task was started in UTC")
_("Completed DateTime")
_("Datetime field when the task was completed in UTC")
_("Traceback")
_("Text of the traceback if the task generated one")
_("Task Meta Information")
_("JSON meta information about the task, such as information on child tasks")
_("task result")
_("task results")
_("Group ID")
_("Celery ID for the Chord header group")
_("JSON serialized list of task result tuples. use .group_result() to decode")
_("Starts at len(chord header) and decrements after each task is finished")
_("Celery ID for the Group that was run")
_("Datetime field when the group result was created in UTC")
_("Datetime field when the group was completed in UTC")
_("group result")
_("group results")

# django celery beat
_("periodic tasks")
_("intervals")
_("crontabs")
_("solar events")
_("clocked")

# jsonform
_("Please correct the errors below.")
