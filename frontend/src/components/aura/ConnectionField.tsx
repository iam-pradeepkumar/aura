import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { DisturbanceState, NodeState } from "../../types/sensing";

const SEGMENTS = 24;

interface ConnectionFieldProps {
  nodes: NodeState[];
  disturbance: DisturbanceState;
}

export function ConnectionField({ nodes, disturbance }: ConnectionFieldProps) {
  const groupRef = useRef<THREE.Group>(null);
  const disturbanceRef = useRef(disturbance);
  disturbanceRef.current = disturbance;

  const { geometries, baseMaterial } = useMemo(() => {
    const geos: THREE.BufferGeometry[] = [];
    for (let i = 0; i < nodes.length; i++) {
      const positions = new Float32Array((SEGMENTS + 1) * 3);
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      geos.push(geo);
    }
    const mat = new THREE.LineBasicMaterial({
      color: new THREE.Color("#00D9FF"),
      transparent: true,
      opacity: 0.14,
      depthWrite: false,
    });
    return { geometries: geos, baseMaterial: mat };
  }, [nodes.length]);

  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;

    const lines: THREE.Line[] = [];
    geometries.forEach((geo) => {
      const line = new THREE.Line(geo, baseMaterial.clone());
      line.frustumCulled = false;
      group.add(line);
      lines.push(line);
    });

    return () => {
      lines.forEach((line) => {
        group.remove(line);
        (line.material as THREE.Material).dispose();
      });
    };
  }, [geometries, baseMaterial]);

  useEffect(() => {
    return () => {
      geometries.forEach((g) => g.dispose());
      baseMaterial.dispose();
    };
  }, [geometries, baseMaterial]);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const dist = disturbanceRef.current;
    const group = groupRef.current;
    if (!group) return;

    nodes.forEach((node, nodeIdx) => {
      const line = group.children[nodeIdx] as THREE.Line | undefined;
      if (!line) return;

      const sx = node.position[0];
      const sz = node.position[2];
      const tx = dist.x;
      const tz = dist.z;

      const positions = (line.geometry.attributes.position as THREE.BufferAttribute).array as Float32Array;

      for (let i = 0; i <= SEGMENTS; i++) {
        const u = i / SEGMENTS;
        let x = sx + (tx - sx) * u;
        let z = sz + (tz - sz) * u;

        const dx = x - dist.x;
        const dz = z - dist.z;
        const distance = Math.sqrt(dx * dx + dz * dz);
        const influence = Math.exp(-(distance * distance) / 4.5);
        const wave = Math.sin(u * 8 - t * 2.2 + nodeIdx * 0.5) * influence * 0.12;

        x += -dz / Math.max(distance, 0.001) * wave;
        z += dx / Math.max(distance, 0.001) * wave;

        const idx = i * 3;
        positions[idx] = x;
        positions[idx + 1] = 0.06 + influence * 0.05;
        positions[idx + 2] = z;
      }

      line.geometry.attributes.position.needsUpdate = true;
      const mat = line.material as THREE.LineBasicMaterial;
      mat.opacity = 0.06 + node.signalStrength * 0.12 + Math.sin(t * 1.4 + nodeIdx) * 0.02;
    });
  });

  return <group ref={groupRef} />;
}
