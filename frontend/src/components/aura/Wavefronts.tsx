import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { DisturbanceState, NodeState } from "../../types/sensing";

const POINTS = 128;
const WAVES_PER_NODE = 3;
const FALLOFF = 2.8;
const BEND_STRENGTH = 1.15;
const Y_HEIGHT = 0.08;

interface WavefrontsProps {
  nodes: NodeState[];
  disturbance: DisturbanceState;
}

interface WaveLine {
  line: THREE.Line;
  nodeIndex: number;
  phaseOffset: number;
  speed: number;
}

export function Wavefronts({ nodes, disturbance }: WavefrontsProps) {
  const groupRef = useRef<THREE.Group>(null);
  const wavesRef = useRef<WaveLine[]>([]);
  const disturbanceRef = useRef(disturbance);

  disturbanceRef.current = disturbance;

  const { geometries, material } = useMemo(() => {
    const geos: THREE.BufferGeometry[] = [];
    const total = nodes.length * WAVES_PER_NODE;

    for (let w = 0; w < total; w++) {
      const positions = new Float32Array(POINTS * 3);
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      geos.push(geo);
    }

    const mat = new THREE.LineBasicMaterial({
      color: new THREE.Color("#00D9FF"),
      transparent: true,
      opacity: 0.42,
      depthWrite: false,
    });

    return { geometries: geos, material: mat };
  }, [nodes.length]);

  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;

    wavesRef.current = [];
    geometries.forEach((geo, idx) => {
      const line = new THREE.Line(geo, material.clone());
      const nodeIndex = Math.floor(idx / WAVES_PER_NODE);
      const phaseOffset = (idx % WAVES_PER_NODE) * 0.85;
      const speed = 0.55 + (idx % WAVES_PER_NODE) * 0.12;
      line.frustumCulled = false;
      group.add(line);
      wavesRef.current.push({ line, nodeIndex, phaseOffset, speed });
    });

    return () => {
      wavesRef.current.forEach(({ line }) => {
        group.remove(line);
        (line.material as THREE.Material).dispose();
      });
      wavesRef.current = [];
    };
  }, [geometries, material]);

  useEffect(() => {
    return () => {
      geometries.forEach((g) => g.dispose());
      material.dispose();
    };
  }, [geometries, material]);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const dist = disturbanceRef.current;

    wavesRef.current.forEach(({ line, nodeIndex, phaseOffset, speed }) => {
      const node = nodes[nodeIndex];
      if (!node) return;

      const sourceX = node.position[0];
      const sourceZ = node.position[2];
      const baseRadius = ((t * speed + phaseOffset) % 4.2) + 0.35;
      const fade = Math.max(0, 1 - (baseRadius - 0.35) / 3.8);

      const positions = (line.geometry.attributes.position as THREE.BufferAttribute).array as Float32Array;

      for (let i = 0; i < POINTS; i++) {
        const theta = (i / (POINTS - 1)) * Math.PI * 2;
        const radius = baseRadius;

        let x = sourceX + Math.cos(theta) * radius;
        let z = sourceZ + Math.sin(theta) * radius;

        const dx = x - dist.x;
        const dz = z - dist.z;
        const distance = Math.sqrt(dx * dx + dz * dz);

        const influence = Math.exp(-(distance * distance) / FALLOFF);

        const compression = 1 - influence * 0.45;
        x = dist.x + dx * compression;
        z = dist.z + dz * compression;

        const tangentX = -dz / Math.max(distance, 0.001);
        const tangentZ = dx / Math.max(distance, 0.001);
        const bend = influence * BEND_STRENGTH * dist.strength;

        x += tangentX * bend;
        z += tangentZ * bend;

        const idx = i * 3;
        positions[idx] = x;
        positions[idx + 1] = Y_HEIGHT + influence * 0.04;
        positions[idx + 2] = z;
      }

      line.geometry.attributes.position.needsUpdate = true;
      const mat = line.material as THREE.LineBasicMaterial;
      mat.opacity = 0.08 + fade * 0.38 * (0.7 + dist.strength * 0.3);
    });
  });

  return <group ref={groupRef} />;
}
