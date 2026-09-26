import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import type { SensingState } from "../../types/sensing";
import { EnvironmentGrid } from "./EnvironmentGrid";
import { SpatialField } from "./SpatialField";
import { Wavefronts } from "./Wavefronts";
import { Disturbance } from "./Disturbance";
import { DetectionLabel } from "./DetectionLabel";
import { ConnectionField } from "./ConnectionField";
import { SensorNode } from "./SensorNode";

interface AuraSceneProps {
  sensingState: SensingState;
  selectedNode: string | null;
  onSelectNode: (id: string) => void;
  onBackgroundClick: () => void;
}

function SceneContent({
  sensingState,
  selectedNode,
  onSelectNode,
  onBackgroundClick,
}: AuraSceneProps) {
  return (
    <>
      <color attach="background" args={["#02070A"]} />
      <fog attach="fog" args={["#02070A", 14, 28]} />
      <ambientLight intensity={0.25} />
      <directionalLight position={[4, 10, 6]} intensity={0.35} color="#19DFFF" />
      <directionalLight position={[-5, 6, -4]} intensity={0.12} color="#0a3040" />

      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, -0.01, 0]}
        onClick={onBackgroundClick}
      >
        <planeGeometry args={[30, 30]} />
        <meshBasicMaterial visible={false} />
      </mesh>

      <EnvironmentGrid />
      <SpatialField disturbance={sensingState.disturbance} />
      <ConnectionField nodes={sensingState.nodes} disturbance={sensingState.disturbance} />
      <Wavefronts nodes={sensingState.nodes} disturbance={sensingState.disturbance} />
      <Disturbance disturbance={sensingState.disturbance} />
      <DetectionLabel disturbance={sensingState.disturbance} />

      {sensingState.nodes.map((node) => (
        <SensorNode
          key={node.id}
          node={node}
          selected={selectedNode === node.id}
          onSelect={onSelectNode}
        />
      ))}

      <OrbitControls
        enablePan={false}
        minDistance={6}
        maxDistance={18}
        minPolarAngle={0.35}
        maxPolarAngle={Math.PI / 2.1}
        target={[0, 0, 0]}
      />
    </>
  );
}

export function AuraScene(props: AuraSceneProps) {
  return (
    <Canvas
      camera={{ position: [0, 8, 9], fov: 45, near: 0.1, far: 50 }}
      gl={{ antialias: true, alpha: false }}
      dpr={[1, 2]}
    >
      <Suspense fallback={null}>
        <SceneContent {...props} />
      </Suspense>
    </Canvas>
  );
}
