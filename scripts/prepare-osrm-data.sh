#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
osrm_data_dir="${OSRM_DATA_DIR:-${repo_root}/infrastructure/geospatial/osrm-data}"
osrm_image="${OSRM_IMAGE:-ghcr.io/project-osrm/osrm-backend:v5.27.1}"
osrm_pbf_url="${OSRM_PBF_URL:-https://download.geofabrik.de/asia/philippines-latest.osm.pbf}"
osrm_pbf_file="${osrm_data_dir}/philippines.osm.pbf"
osrm_pbf_complete="${osrm_pbf_file}.download-complete"
osrm_graph_base="${osrm_data_dir}/philippines.osrm"
osrm_graph_sentinel="${osrm_graph_base}.hsgr"
dataset_version="${OSRM_DATASET_VERSION:-philippines-$(date -u +%Y-%m-%d)}"
validation_container="openci-osrm-validate-$$"

cleanup() {
  docker rm -f "${validation_container}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

mkdir -p "${osrm_data_dir}"
if [[ ! -f "${osrm_pbf_complete}" ]]; then
  curl \
    --fail \
    --location \
    --continue-at - \
    --connect-timeout 30 \
    --retry 8 \
    --retry-all-errors \
    --retry-delay 2 \
    --speed-limit 1024 \
    --speed-time 60 \
    "${osrm_pbf_url}" \
    --output "${osrm_pbf_file}"
  touch "${osrm_pbf_complete}"
fi

if [[ ! -s "${osrm_graph_sentinel}" ]]; then
  docker run --rm \
    --volume "${osrm_data_dir}:/data" \
    "${osrm_image}" \
    osrm-extract -p /opt/car.lua /data/philippines.osm.pbf
  docker run --rm \
    --volume "${osrm_data_dir}:/data" \
    "${osrm_image}" \
    osrm-contract /data/philippines.osrm
fi

required_graph_artifacts=(
  "${osrm_graph_base}.fileIndex"
  "${osrm_graph_base}.geometry"
  "${osrm_graph_base}.hsgr"
  "${osrm_graph_base}.names"
  "${osrm_graph_base}.properties"
  "${osrm_graph_base}.ramIndex"
  "${osrm_graph_base}.timestamp"
)
for artifact in "${required_graph_artifacts[@]}"; do
  if [[ ! -s "${artifact}" ]]; then
    printf 'OSRM preparation did not produce required artifact %s\n' "${artifact}" >&2
    exit 1
  fi
done

docker run --rm --detach \
  --name "${validation_container}" \
  --publish 127.0.0.1::5000 \
  --volume "${osrm_data_dir}:/data:ro" \
  "${osrm_image}" \
  osrm-routed --algorithm ch --max-table-size 100 /data/philippines.osrm \
  >/dev/null

validation_port="$(docker port "${validation_container}" 5000/tcp | head -n 1)"
validation_port="${validation_port##*:}"
validated=false
for _ in $(seq 1 30); do
  nearest_ok=false
  route_ok=false
  if curl --fail --silent \
    "http://127.0.0.1:${validation_port}/nearest/v1/driving/121.0000,14.5000?number=1" \
    | grep -q '"code":"Ok"'; then
    nearest_ok=true
  fi
  if curl --fail --silent \
    "http://127.0.0.1:${validation_port}/route/v1/driving/121.0000,14.5000;121.0100,14.5100?overview=false" \
    | grep -q '"code":"Ok"'; then
    route_ok=true
  fi
  if [[ "${nearest_ok}" == true && "${route_ok}" == true ]]; then
    validated=true
    break
  fi
  sleep 2
done
if [[ "${validated}" != true ]]; then
  printf 'Prepared OSRM graph failed the Metro Manila Nearest/Route validation.\n' >&2
  docker logs "${validation_container}" >&2 || true
  exit 1
fi

printf '%s\n' "${dataset_version}" > "${osrm_data_dir}/data-version.txt"
printf 'OSRM data prepared and validated in %s\n' "${osrm_data_dir}"
printf 'Set OSRM_DATASET_VERSION=%s in .env before starting the planning services.\n' "${dataset_version}"
