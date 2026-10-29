#!/bin/bash
# Validate BEFORE the official entrypoint can initialize any users/volume.
set -eu
if [[ ! ${MONGO_PASSWORD:-} =~ ^[a-f0-9]{64}$ ]] || [[ ! ${MONGO_INITDB_ROOT_PASSWORD:-} =~ ^[a-f0-9]{64}$ ]] || [[ ${MONGO_PASSWORD:-} == ${MONGO_INITDB_ROOT_PASSWORD:-} ]]; then
  echo MONGO_PRIVATE_CONFIGURATION_INVALID >&2
  exit 1
fi
exec /usr/local/bin/docker-entrypoint.sh "$@"
