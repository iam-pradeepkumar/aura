#!/usr/bin/env bash
# Spawn kinematic rover model into Gazebo (post world load)
set -e
sleep 2
gz service -s /world/aura_disaster_zone/create \
  --reqtype gz.msgs.EntityFactory \
  --reptype gz.msgs.Boolean \
  --timeout 5000 \
  --req 'sdf_filename: "model://aura_rover", name: "aura_rover_1", pose: {position: {x: 4, y: 4, z: 0.2}}' \
  2>/dev/null || echo "aura_rover spawn skipped (Gazebo model path optional)"
