import { useMemo } from "react";
import * as THREE from "three";

const SIZE_X = 12.5;
const SIZE_Z = 9.5;
const DIVISIONS_X = 24;
const DIVISIONS_Z = 18;

export function EnvironmentGrid() {
  const geometry = useMemo(() => {
    const points: number[] = [];
    const stepX = SIZE_X / DIVISIONS_X;
    const stepZ = SIZE_Z / DIVISIONS_Z;
    const halfX = SIZE_X / 2;
    const halfZ = SIZE_Z / 2;

    for (let i = 0; i <= DIVISIONS_Z; i++) {
      const p = -halfZ + i * stepZ;
      points.push(-halfX, 0.002, p, halfX, 0.002, p);
    }
    for (let i = 0; i <= DIVISIONS_X; i++) {
      const p = -halfX + i * stepX;
      points.push(p, 0.002, -halfZ, p, 0.002, halfZ);
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
    return geo;
  }, []);

  const material = useMemo(
    () =>
      new THREE.LineBasicMaterial({
        color: new THREE.Color("#0a2a32"),
        transparent: true,
        opacity: 0.35,
      }),
    [],
  );

  return <lineSegments geometry={geometry} material={material} />;
}
