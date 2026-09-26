import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { DisturbanceState } from "../../types/sensing";

interface DisturbanceProps {
  disturbance: DisturbanceState;
}

export function Disturbance({ disturbance }: DisturbanceProps) {
  const glowRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  const pulseRef = useRef<THREE.Mesh>(null);

  const glowMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: new THREE.Color("#00D9FF"),
        transparent: true,
        opacity: 0.12,
        depthWrite: false,
      }),
    [],
  );

  const ringMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: new THREE.Color("#19DFFF"),
        transparent: true,
        opacity: 0.22,
        wireframe: true,
        depthWrite: false,
      }),
    [],
  );

  const pulseMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: new THREE.Color("#FFB000"),
        transparent: true,
        opacity: 0.08,
        depthWrite: false,
      }),
    [],
  );

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const pulse = 0.85 + Math.sin(t * 2.1) * 0.12;
    const s = disturbance.strength;

    if (glowRef.current) {
      glowRef.current.scale.setScalar(0.9 + s * 0.35 * pulse);
      (glowRef.current.material as THREE.MeshBasicMaterial).opacity = 0.08 + s * 0.1;
    }
    if (ringRef.current) {
      ringRef.current.rotation.y = t * 0.15;
      ringRef.current.scale.setScalar(0.7 + s * 0.25);
    }
    if (pulseRef.current) {
      pulseRef.current.scale.setScalar(1.1 + Math.sin(t * 1.6) * 0.15);
      (pulseRef.current.material as THREE.MeshBasicMaterial).opacity = 0.05 + s * 0.06;
    }
  });

  return (
    <group position={[disturbance.x, 0.1, disturbance.z]}>
      <mesh ref={glowRef} material={glowMat}>
        <sphereGeometry args={[0.55, 24, 16]} />
      </mesh>
      <mesh ref={ringRef} rotation={[-Math.PI / 2, 0, 0]} material={ringMat}>
        <ringGeometry args={[0.35, 0.55, 48]} />
      </mesh>
      <mesh ref={pulseRef} rotation={[-Math.PI / 2, 0, 0]} material={pulseMat}>
        <ringGeometry args={[0.55, 0.75, 48]} />
      </mesh>
    </group>
  );
}
