# Before building the image you need to use poetry:
# rm dist/*.whl
# poetry build
# poetry export --only main > dist/requirements-export.txt

FROM alpine:latest as base
RUN apk add --no-cache python3

FROM base as build
RUN apk add --no-cache py3-pip
RUN python3 -m venv /app
COPY /dist /dist
RUN source /app/bin/activate && pip install -r /dist/requirements-export.txt
RUN source /app/bin/activate && pip install /dist/*.whl

FROM base as final
COPY --from=build /app /app
ENV PATH="/app/bin/:$PATH"
CMD ["dynamic-dns-aws"]
