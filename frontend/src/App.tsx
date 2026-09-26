import { useCallback } from "react";
import { AuraScene } from "./components/aura/AuraScene";
import { Header } from "./components/ui/Header";
import { TelemetryOverlay } from "./components/ui/TelemetryOverlay";
import { NodeInspector } from "./components/ui/NodeInspector";
import { useSensingSimulation } from "./hooks/useSensingSimulation";

export default function App() {
  const { sensingState, selectedNode, setSelectedNode } = useSensingSimulation();

  const handleBackgroundClick = useCallback(() => {
    setSelectedNode(null);
  }, [setSelectedNode]);

  const selected = sensingState.nodes.find((n) => n.id === selectedNode) ?? null;

  return (
    <div className="app-root">
      <div className="scene-layer">
        <AuraScene
          sensingState={sensingState}
          selectedNode={selectedNode}
          onSelectNode={setSelectedNode}
          onBackgroundClick={handleBackgroundClick}
        />
      </div>
      <div className="ui-layer">
        <Header />
        <TelemetryOverlay sensingState={sensingState} />
        {selected && (
          <NodeInspector node={selected} onClose={() => setSelectedNode(null)} />
        )}
      </div>
    </div>
  );
}
