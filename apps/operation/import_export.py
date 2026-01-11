from import_export.instance_loaders import BaseInstanceLoader
from import_export.resources import ModelResource

from apps.operation.models import Category


class CategoryResource(ModelResource):
    class Meta:
        model = Category
        fields = ("name", "ancestors")
        import_id_fields = ("name", "ancestors")
        skip_unchanged = True

    def get_instance(self, instance_loader: BaseInstanceLoader, row: dict[str, str] | list[str]):
        name = row.get("name") if isinstance(row, dict) else row[0]
        ancestors_str = row.get("ancestors") if isinstance(row, dict) else row[1]
        if not name:
            return None
        ancestors = ancestors_str.split(",") if ancestors_str else []
        return Category.objects.filter(name=name, ancestors=ancestors).first()

    def save_instance(self, instance: Category, *args: object, **kwargs: object):
        dry_run = kwargs.get("dry_run", False)
        if dry_run:
            return

        name = instance.name
        ancestors = getattr(instance, "ancestors", [])

        if Category.objects.filter(name=name, ancestors=ancestors).exists():
            return

        if len(ancestors) >= 1:
            root_name = ancestors[0]
            if not Category.objects.filter(name=root_name, ancestors=[]).exists():
                Category.add_root(name=root_name)

        if len(ancestors) >= 2:
            parent_name = ancestors[1]
            if not Category.objects.filter(name=parent_name, ancestors=ancestors[:1]).exists():
                root = Category.objects.filter(name=ancestors[0], ancestors=[]).first()
                if root:
                    root.add_child(name=parent_name)

        if len(ancestors) == 0:
            Category.add_root(name=name)

        elif len(ancestors) == 1:
            parent = Category.objects.filter(name=ancestors[0], ancestors=[]).first()
            if parent:
                parent.add_child(name=name)

        elif len(ancestors) == 2:
            parent = Category.objects.filter(name=ancestors[1], ancestors=ancestors[:1]).first()
            if parent:
                parent.add_child(name=name)
