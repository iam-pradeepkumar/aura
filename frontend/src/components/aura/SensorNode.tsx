import { useMemo, useRef, useState } from "react";
import { Html } from "@react-three/drei";
import { ThreeEvent, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { NodeState } from "../../types/sensing";

interface SensorNodeProps {
  node: NodeState;
  selected: boolean;
  onSelect: (id: string) => void;
}

export function SensorNode({ node, selected, onSelect }: SensorNodeProps) {
  const [hovered, setHovered] = useState(false);
  const glowRef = useRef<THREE.Mesh>(null);
  const lightRef = useRef<THREE.Mesh>(null);

  const bodyMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: new THREE.Color("#0a1820"),
        metalness: 0.4,
        roughness: 0.65,
      }),
    [],
  );

  const ringMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: new THREE.Color("#00D9FF"),
        transparent: true,
        opacity: 0.25,
        depthWrite: false,
      }),
    [],
  );

  const glowMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: new THREE.Color("#00D9FF"),
        transparent: true,
        opacity: 0.08,
        depthWrite: false,
      }),
    [],
  );

  const lightMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: new THREE.Color("#46F5C4"),
        transparent: true,
        opacity: 0.9,
      }),
    [],
  );

  const handleClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    onSelect(node.id);
  };

  useFrame(() => {
    if (!glowRef.current) return;
    const glowIntensity = selected ? 0.22 : hovered ? 0.16 : 0.08;
    (glowRef.current.material as THREE.MeshBasicMaterial).opacity = glowIntensity;
  });

  return (
    <group position={node.position}>
      <mesh
        onClick={handleClick}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHovered(true);
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={() => {
          setHovered(false);
          document.body.style.cursor = "default";
        }}
        material={bodyMat}
        castShadow
      >
        <boxGeometry args={[0.22, 0.1, 0.16]} />
      </mesh>

      <mesh ref={glowRef} position={[0, 0.08, 0]} material={glowMat}>
        <sphereGeometry args={[0.18, 12, 8]} />
      </mesh>

      <mesh ref={lightRef} position={[0, 0.06, 0.09]} material={lightMat}>
        <sphereGeometry args={[0.025, 8, 8]} />
      </mesh>

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]} material={ringMat}>
        <ringGeometry args={[0.14, 0.2, 32]} />
      </mesh>

      <Html position={[0, 0.22, 0]} center distanceFactor={10} style={{ pointerEvents: "none" }}>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "8px",
            color: selected ? "#00D9FF" : "#4A9CA9",
            letterSpacing: "0.06em",
          }}
        >
          {node.id}
        </span>
      </Html>
    </group>
  );
}
