import { useMemo } from "react";
import * as THREE from "three";

const SIZE = 14;
const DIVISIONS = 28;

export function EnvironmentGrid() {
  const geometry = useMemo(() => {
    const points: number[] = [];
    const step = SIZE / DIVISIONS;
    const half = SIZE / 2;

    for (let i = 0; i <= DIVISIONS; i++) {
      const p = -half + i * step;
      points.push(-half, 0.002, p, half, 0.002, p);
      points.push(p, 0.002, -half, p, 0.002, half);
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
