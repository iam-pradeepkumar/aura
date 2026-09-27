import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, type MutableRefObject } from "react";
import {
  Color,
  DoubleSide,
  Group,
  MathUtils,
  OrthographicCamera,
  Quaternion,
  Vector3,
} from "three";
import type { MotionState } from "./motion";
import { stepPlanet, stepRunner } from "./motion";

const up = new Vector3(0, 1, 0);

function ResponsiveCamera() {
  const { size, camera } = useThree();
  useEffect(() => {
    const ortho = camera as OrthographicCamera;
    ortho.zoom = size.width / (size.width < 700 ? 5.65 : 5.25);
    ortho.updateProjectionMatrix();
  }, [size.width, size.height, camera]);
  return null;
}

function DisasterGlobe({ motion, auto, reduced }: WorldProps) {
  const planet = useRef<Group>(null);
  const runner = useRef<Group>(null);
  const drone = useRef<Group>(null);
  const inverse = useRef(new Quaternion());
  const localTop = useRef(new Vector3());
  const pulse = useRef(0);

  useFrame(({ camera }, delta) => {
    const m = motion.current;
    const elapsed = Math.min(delta, 0.05);
    const count = Math.ceil(elapsed / (1 / 120));
    for (let i = 0; i < count; i++) {
      const dt = elapsed / count;
      stepPlanet(m, dt, auto, reduced, -0.028);
      if (m.dragging) {
        m.pitchVelocity +=
          (70 * (m.pitchTarget - m.pitchAngle) - 17 * m.pitchVelocity) * dt;
      } else {
        m.pitchVelocity = MathUtils.damp(m.pitchVelocity, 0, 6, dt);
      }
      m.pitchVelocity = MathUtils.clamp(m.pitchVelocity, -0.55, 0.55);
      m.pitchAngle += m.pitchVelocity * dt;
      if (planet.current) {
        planet.current.rotation.y = m.planetAngle;
        planet.current.rotation.x = m.pitchAngle * 0.35;
      }
      inverse.current.copy(planet.current?.quaternion ?? new Quaternion()).invert();
      localTop.current.copy(up).applyQuaternion(camera.quaternion).applyQuaternion(inverse.current);
      stepRunner(m, dt, Math.atan2(localTop.current.x, localTop.current.y), reduced);
    }

    pulse.current += elapsed;
    const angle = m.planetAngle + m.characterAngle;
    const radius = 2.25;
    if (runner.current) {
      runner.current.position.set(
        Math.sin(angle) * radius,
        Math.cos(angle) * radius,
        0.08,
      );
      runner.current.rotation.z = -angle;
      runner.current.rotation.x = Math.sin(m.phase) * 0.08 * m.activity;
    }
    if (drone.current) {
      const hover = Math.sin(pulse.current * 2.2) * 0.12;
      drone.current.position.set(
        Math.sin(angle + 0.9) * (radius + 0.55),
        Math.cos(angle + 0.9) * (radius + 0.55) + hover,
        0.45,
      );
      drone.current.rotation.z = -angle - 0.9;
    }
  });

  return (
    <>
      <group ref={planet}>
        <mesh>
          <sphereGeometry args={[2.25, 64, 48]} />
          <meshStandardMaterial
            color="#1a2838"
            roughness={0.82}
            metalness={0.08}
            emissive="#0a1520"
            emissiveIntensity={0.35}
          />
        </mesh>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[2.32, 2.48, 64]} />
          <meshBasicMaterial color="#f97316" transparent opacity={0.35} side={DoubleSide} />
        </mesh>
        {[0, 1, 2, 3, 4].map((i) => (
          <mesh
            key={i}
            position={[
              Math.sin(i * 1.25) * 1.7,
              Math.cos(i * 1.25) * 1.7,
              1.35,
            ]}
          >
            <boxGeometry args={[0.22, 0.08, 0.18]} />
            <meshStandardMaterial color="#2d3f52" roughness={0.9} />
          </mesh>
        ))}
        <mesh position={[0.6, 1.4, 1.2]}>
          <sphereGeometry args={[0.14, 12, 12]} />
          <meshStandardMaterial
            color="#fbbf24"
            emissive="#f97316"
            emissiveIntensity={1.8}
          />
        </mesh>
      </group>

      <group ref={runner}>
        <SpiderBot />
      </group>
      <group ref={drone}>
        <RescueDrone />
      </group>
    </>
  );
}

function SpiderBot() {
  const legs = useMemo(() => Array.from({ length: 4 }, (_, i) => i), []);
  return (
    <group scale={0.55}>
      <mesh position={[0, 0.12, 0]}>
        <boxGeometry args={[0.42, 0.14, 0.32]} />
        <meshStandardMaterial color="#334155" metalness={0.4} roughness={0.5} />
      </mesh>
      <mesh position={[0, 0.22, 0.08]}>
        <boxGeometry args={[0.18, 0.08, 0.12]} />
        <meshStandardMaterial color="#1e293b" />
      </mesh>
      {legs.map((i) => (
        <mesh
          key={i}
          position={[
            (i % 2 === 0 ? -1 : 1) * 0.22,
            -0.02,
            (i < 2 ? -1 : 1) * 0.16,
          ]}
          rotation={[0.5, 0, (i % 2 === 0 ? -1 : 1) * 0.4]}
        >
          <boxGeometry args={[0.04, 0.22, 0.04]} />
          <meshStandardMaterial color="#475569" />
        </mesh>
      ))}
      <mesh position={[0, 0.28, 0.12]}>
        <sphereGeometry args={[0.04, 8, 8]} />
        <meshStandardMaterial
          color="#22d3ee"
          emissive="#06b6d4"
          emissiveIntensity={2}
        />
      </mesh>
    </group>
  );
}

function RescueDrone() {
  return (
    <group scale={0.5}>
      <mesh>
        <boxGeometry args={[0.36, 0.06, 0.36]} />
        <meshStandardMaterial color="#1e293b" metalness={0.5} roughness={0.4} />
      </mesh>
      {[0, 1, 2, 3].map((i) => (
        <group
          key={i}
          position={[
            (i % 2 === 0 ? -1 : 1) * 0.28,
            0.04,
            (i < 2 ? -1 : 1) * 0.28,
          ]}
        >
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.18, 0.18, 0.02, 16]} />
            <meshStandardMaterial color="#64748b" transparent opacity={0.35} />
          </mesh>
        </group>
      ))}
      <mesh position={[0, -0.06, 0]}>
        <coneGeometry args={[0.05, 0.1, 8]} />
        <meshStandardMaterial color="#f97316" emissive="#ea580c" emissiveIntensity={1.2} />
      </mesh>
    </group>
  );
}

type WorldProps = {
  motion: MutableRefObject<MotionState>;
  auto: boolean;
  reduced: boolean;
};

function SarWorld(props: WorldProps) {
  const { size, camera } = useThree();
  useEffect(() => {
    const ortho = camera as OrthographicCamera;
    ortho.zoom = Math.min(size.width / 5.6, size.height / 6.05);
    ortho.updateProjectionMatrix();
  }, [size, camera]);

  const centerY = size.height / (size.width / (size.width < 700 ? 5.65 : 5.25)) * (size.width < 700 ? 0.08 : 0.16) - 2.1;

  return (
    <group position={[0, centerY, 0]}>
      <DisasterGlobe {...props} />
    </group>
  );
}

type SarPlanetSceneProps = WorldProps & {
  active: boolean;
  onReady?: (ready: boolean) => void;
};

export function SarPlanetScene({ active, onReady, ...props }: SarPlanetSceneProps) {
  useEffect(() => {
    onReady?.(true);
  }, [onReady]);

  const lowPower =
    typeof window !== "undefined" &&
    (window.matchMedia("(pointer: coarse)").matches ||
      (navigator.hardwareConcurrency || 8) <= 4);

  return (
    <Canvas
      orthographic
      camera={{ position: [0, 0, 9], zoom: 150, near: 0.1, far: 30 }}
      dpr={lowPower ? [1, 1.25] : [1, 2]}
      frameloop={active ? "always" : "never"}
      gl={{ antialias: true, alpha: true, powerPreference: lowPower ? "low-power" : "high-performance" }}
      onCreated={({ gl }) => {
        gl.setClearColor(new Color("#000000"), 0);
      }}
    >
      <ResponsiveCamera />
      <ambientLight intensity={0.85} />
      <hemisphereLight args={["#dbeafe", "#1e293b", 1.2]} />
      <directionalLight position={[-3, 5, 5]} intensity={2.4} color="#fff7ed" />
      <directionalLight position={[3, 2, -2]} intensity={1.6} color="#7dd3fc" />
      <pointLight position={[0, 0, 4]} intensity={0.8} color="#f97316" />
      <SarWorld {...props} />
    </Canvas>
  );
}
