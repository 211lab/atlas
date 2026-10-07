FROM python:3.12.10-alpine3.21 AS build
WORKDIR /build
COPY requirements-docs.txt mkdocs.yml ./
RUN pip install --no-cache-dir -r requirements-docs.txt
COPY docs/ docs/
RUN test -f docs/index.md && mkdocs build --strict --site-dir /tmp/opencode/atlas-docs-site

FROM busybox:1.37.0-musl
COPY --from=build /tmp/opencode/atlas-docs-site/ /www/
USER 65534:65534
EXPOSE 8080
CMD ["httpd", "-f", "-p", "8080", "-h", "/www"]
