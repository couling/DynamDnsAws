#!/bin/sh

set -ex

project_dir="$(dirname "$0")"

rm -rf "$project_dir/dist"

poetry self add poetry-dynamic-versioning
poetry build
poetry export --only main > "dist/requirements-export.txt"

# shellcheck disable=SC2039
read package_name version << EOF
$(poetry version | sed 's/+/_/g')
EOF

docker buildx create --name "${package_name}_builder" --bootstrap --use --driver-opt network=host
trap "docker buildx stop '${package_name}_builder' && docker buildx rm  '${package_name}_builder'" EXIT
docker buildx build --push \
  --platform linux/arm/v6,linux/arm/v7,linux/arm64/v8,linux/amd64,linux/386  \
  --tag "couling/${package_name}:${version}" \
  --tag "couling/${package_name}:latest" \
  "$project_dir"
