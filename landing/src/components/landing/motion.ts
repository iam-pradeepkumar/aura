export const GAIT_DISTANCE = 0.44;

export type MotionState = {
  planetAngle: number;
  planetVelocity: number;
  dragTarget: number;
  characterTarget: number;
  characterAngle: number;
  characterVelocity: number;
  phase: number;
  activity: number;
  direction: number;
  time: number;
  dragging: boolean;
  lastInteraction: number;
  pitchAngle: number;
  pitchVelocity: number;
  pitchTarget: number;
  heading?: number;
  cameraHeading?: number;
};

export const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

export const damp = (value: number, target: number, lambda: number, dt: number) =>
  value + (target - value) * (1 - Math.exp(-lambda * dt));

export const smoothstep = (value: number, min: number, max: number) => {
  const t = clamp((value - min) / (max - min), 0, 1);
  return t * t * (3 - 2 * t);
};

export function createMotion(): MotionState {
  return {
    planetAngle: 0,
    planetVelocity: 0,
    dragTarget: 0,
    characterTarget: 0,
    characterAngle: 0,
    characterVelocity: 0,
    phase: 0,
    activity: 0,
    direction: 1,
    time: 0,
    dragging: false,
    lastInteraction: 0,
    pitchAngle: 0,
    pitchVelocity: 0,
    pitchTarget: 0,
  };
}

export function stepPlanet(
  m: MotionState,
  dt: number,
  auto: boolean,
  reduced: boolean,
  autoRoll = -0.032,
) {
  m.time += dt;
  if (!auto) {
    m.dragging = false;
    m.planetVelocity = 0;
    m.pitchVelocity = 0;
    m.dragTarget = m.planetAngle;
    m.pitchTarget = m.pitchAngle;
    return;
  }
  if (m.dragging) {
    const acceleration =
      90 * (m.dragTarget - m.planetAngle) - 18 * m.planetVelocity;
    m.planetVelocity += acceleration * dt;
  } else {
    const desired =
      auto && !reduced && m.time - m.lastInteraction > 3.5 ? autoRoll : 0;
    m.planetVelocity = damp(m.planetVelocity, desired, reduced ? 12 : 5, dt);
  }
  m.planetVelocity = clamp(m.planetVelocity, -1.15, 1.15);
  m.planetAngle += m.planetVelocity * dt;
}

export function stepRunner(
  m: MotionState,
  dt: number,
  screenTopLocal: number,
  reduced: boolean,
) {
  m.characterTarget += Math.atan2(
    Math.sin(screenTopLocal - m.characterTarget),
    Math.cos(screenTopLocal - m.characterTarget),
  );
  const error = m.characterTarget - m.characterAngle;
  const stiffness = reduced ? 110 : 48;
  const damping = reduced ? 21 : 11;
  m.characterVelocity += (stiffness * error - damping * m.characterVelocity) * dt;
  m.characterAngle += m.characterVelocity * dt;
  const speed = Math.abs(m.characterVelocity);
  m.activity = damp(m.activity, smoothstep(speed, 4e-3, 0.022), 9, dt);
  if (speed > 0.025) m.direction = Math.sign(m.characterVelocity);
  m.phase += (speed * 2.25 / GAIT_DISTANCE) * Math.PI * 2 * dt;
}
