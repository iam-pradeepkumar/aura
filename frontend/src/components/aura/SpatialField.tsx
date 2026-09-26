import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { DisturbanceState } from "../../types/sensing";

const GRID_X = 48;
const GRID_Z = 36;
const SPAN_X = 12;
const SPAN_Z = 9;
const FALLOFF = 3.4;

interface SpatialFieldProps {
  disturbance: DisturbanceState;
}

export function SpatialField({ disturbance }: SpatialFieldProps) {
  const pointsRef = useRef<THREE.Points>(null);
  const disturbanceRef = useRef(disturbance);
  disturbanceRef.current = disturbance;

  const { geometry, basePositions } = useMemo(() => {
    const count = GRID_X * GRID_Z;
    const positions = new Float32Array(count * 3);
    const base = new Float32Array(count * 3);
    const stepX = SPAN_X / (GRID_X - 1);
    const stepZ = SPAN_Z / (GRID_Z - 1);
    const halfX = SPAN_X / 2;
    const halfZ = SPAN_Z / 2;
    let i = 0;

    for (let row = 0; row < GRID_Z; row++) {
      for (let col = 0; col < GRID_X; col++) {
        const x = -halfX + col * stepX;
        const z = -halfZ + row * stepZ;
        base[i] = x;
        base[i + 1] = 0.03;
        base[i + 2] = z;
        positions[i] = x;
        positions[i + 1] = 0.03;
        positions[i + 2] = z;
        i += 3;
      }
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));

    return { geometry: geo, basePositions: base };
  }, []);

  const material = useMemo(
    () =>
      new THREE.PointsMaterial({
        color: new THREE.Color("#19DFFF"),
        size: 0.035,
        transparent: true,
        opacity: 0.22,
        depthWrite: false,
        sizeAttenuation: true,
      }),
    [],
  );

  useEffect(() => {
    return () => {
      geometry.dispose();
      material.dispose();
    };
  }, [geometry, material]);

  useFrame(({ clock }) => {
    const points = pointsRef.current;
    if (!points) return;

    const dist = disturbanceRef.current;
    const t = clock.elapsedTime;
    const attr = geometry.attributes.position as THREE.BufferAttribute;
    const arr = attr.array as Float32Array;

    for (let i = 0; i < basePositions.length; i += 3) {
      const bx = basePositions[i];
      const bz = basePositions[i + 2];

      const dx = bx - dist.x;
      const dz = bz - dist.z;
      const distance = Math.sqrt(dx * dx + dz * dz);
      const influence = Math.exp(-(distance * distance) / FALLOFF);

      const ripple = Math.sin(distance * 3.2 - t * 2.4) * influence * 0.08;
      const lift = influence * dist.strength * 0.14;

      arr[i] = bx + (dist.x - bx) * influence * 0.04;
      arr[i + 1] = 0.03 + lift + ripple;
      arr[i + 2] = bz + (dist.z - bz) * influence * 0.04;
    }

    attr.needsUpdate = true;

    const mat = points.material as THREE.PointsMaterial;
    mat.opacity = 0.14 + dist.strength * 0.12;
    mat.size = 0.028 + dist.strength * 0.018;
  });

  return <points ref={pointsRef} geometry={geometry} material={material} />;
}
