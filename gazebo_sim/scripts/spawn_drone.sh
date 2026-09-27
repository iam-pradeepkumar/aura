#!/usr/bin/env bash
set -e
sleep 2
gz service -s /world/aura_disaster_zone/create \
  --reqtype gz.msgs.EntityFactory \
  --reptype gz.msgs.Boolean \
  --timeout 5000 \
  --req 'sdf_filename: "model://aura_drone", name: "aura_drone_1", pose: {position: {x: 4, y: 4, z: 6}}' \
  2>/dev/null || echo "aura_drone spawn skipped (Gazebo model path optional)"
