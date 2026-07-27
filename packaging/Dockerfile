# ConfigGen CLI-only image (§16) - no GUI, no PySide6/Qt. For teams who
# want a local service or CI usage:
#
#   docker build -t configgen:latest -f packaging/Dockerfile .
#   docker run --rm -v ./my-configs:/app/resources configgen:latest list
#   docker run --rm -v ./my-configs:/app/resources configgen:latest \
#       generate widget --values values.json --api-key <key>
#
# `pip install .` (not `.[gui]`) pulls only the base dependencies -
# PyYAML/Jinja2/pydantic/openpyxl - never PySide6, so the image stays
# small and never needs Qt's system libraries.

FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir .

# Config packs, users.db, and generated output all live under here -
# mount your own directory over it to bring real schemas/templates and
# persist state across container runs.
VOLUME ["/app/resources"]

ENTRYPOINT ["configgen"]
CMD ["--help"]
