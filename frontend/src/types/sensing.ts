export interface NodeState {
  id: string;
  position: [number, number, number];
  online: boolean;
  signalStrength: number;
}

export interface DisturbanceState {
  x: number;
  z: number;
  strength: number;
  humanProbability: number;
}

export interface CSIState {
  frequency: string;
  phaseShift: number;
  doppler: number;
}

export interface SensingState {
  nodes: NodeState[];
  disturbance: DisturbanceState;
  csi: CSIState;
}
