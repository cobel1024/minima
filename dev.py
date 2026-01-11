import subprocess

import typer

app = typer.Typer()


@app.command()
def up():
    subprocess.run(["docker", "build", "--target", "dev", "-t", "minima:dev", "."])
    subprocess.run(["docker", "build", "-t", "minima-search:dev", "-f", "Dockerfile.search", "."])
    subprocess.run(["docker", "network", "create", "minima"])
    subprocess.run(["docker", "compose", "up", "-d"])


@app.command()
def bootstrap():
    commands = [
        "python manage.py migrate",
        "python manage.py collectstatic --noinput",
        "python manage.py createsuperuser --noinput || true",
        "python manage.py create_assistant_bot",
        "python manage.py opensearch index create --force --ignore-error",
        "python manage.py create_platform_partner",
        "python manage.py create_empty_policies",
        "python manage.py convert_mjml",
        "python manage.py load_ncs_data",
    ]

    subprocess.run(["docker", "compose", "exec", "minima", "sh", "-c", " && ".join(commands)])
    subprocess.run(["docker", "compose", "restart", "minima", "worker"])


@app.command()
def lint():
    subprocess.run(["ty", "check"])
    subprocess.run(["ruff", "check", "."])
    subprocess.run(["ruff", "check", "--select", "I", "."])
    subprocess.run(["ruff", "format", "."])


if __name__ == "__main__":
    app()
