import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copy_members(apps, schema_editor):
    """Carry every existing workspace member over, keeping their old global role."""
    Workspace = apps.get_model("app", "Workspace")
    Membership = apps.get_model("app", "Membership")
    for ws in Workspace.objects.all():
        for user in ws.members.all():
            group = user.groups.first()
            role = group.name if group and group.name in ("admin", "editor", "viewer") else "viewer"
            Membership.objects.get_or_create(workspace=ws, user=user, defaults={"role": role})
        # Every workspace needs someone who can manage it: promote its earliest member.
        if not Membership.objects.filter(workspace=ws, role="admin").exists():
            first = Membership.objects.filter(workspace=ws).order_by("id").first()
            if first:
                first.role = "admin"
                first.save(update_fields=["role"])


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0008_add_txt_md_file_types"),
    ]

    operations = [
        migrations.CreateModel(
            name="Membership",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(
                    choices=[("admin", "admin"), ("editor", "editor"), ("viewer", "viewer")],
                    default="viewer", max_length=10,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="memberships", to=settings.AUTH_USER_MODEL,
                )),
                ("workspace", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="memberships", to="app.workspace",
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="membership",
            constraint=models.UniqueConstraint(fields=("workspace", "user"), name="unique_workspace_member"),
        ),
        migrations.RunPython(copy_members, migrations.RunPython.noop),
        migrations.RemoveField(model_name="workspace", name="members"),
        migrations.AddField(
            model_name="workspace",
            name="members",
            field=models.ManyToManyField(
                related_name="workspaces", through="app.Membership", to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
