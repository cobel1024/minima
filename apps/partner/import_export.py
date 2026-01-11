from datetime import datetime

from import_export.fields import Field
from import_export.resources import ModelResource
from import_export.widgets import CharWidget

from apps.partner.models import Employee


class EmployeeResource(ModelResource):
    id_number = Field(attribute="encrypted_id_number", column_name="id_number", widget=CharWidget(allow_blank=True))

    class Meta:
        model = Employee
        skip_unchanged = True
        export_order = ("id", "cohort", "name", "email", "birth_date", "id_number")
        import_order = export_order
        exclude = ("created", "modified", "encrypted_id_number", "user")

    def before_import_row(self, row, **kwargs):
        for k, v in row.items():
            if isinstance(v, datetime) and k == "birth_date":
                row[k] = v.date()
            elif isinstance(v, str):
                row[k] = v.strip()

        if "id_number" in row and row["id_number"]:
            row["id_number"] = Employee.encrypt_id_number(row["id_number"])
        elif "id_number" in row:
            del row["id_number"]

        super().before_import_row(row, **kwargs)

    def dehydrate_id_number(self, obj):
        return ""
